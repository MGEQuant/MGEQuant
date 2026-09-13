#!/usr/bin/env python3
"""Generate NQ_HybridEdge.cs - single source of truth, one ordered write.

WHY THIS REPLACES build.py AND create.py
----------------------------------------
Both of those were several standalone "write part N" scripts concatenated end
to end. That produced four compounding faults:
  1. C# left outside string literals -> SyntaxError, so neither ever ran
  2. a SECOND open(path, 'w') mid-script that truncated everything written above
  3. parts written out of order (p2, p1, p5, p4, p3, p2, ...)
  4. each part defined 2-3 times, later definitions silently winning
The visible symptoms were a duplicate OnStateChange(), a duplicate
MeanReversionScore property, and a 24-byte .cs file.

This script holds the C# in ONE string, writes ONCE, then verifies the result
before exiting. There are no parts and nothing to order.

FIXES APPLIED to the v2.0 logic (documented, deliberate):
  1. CheckExit() used the CURRENT bar's directionalBias to choose the exit
     branch. Bias recomputes every bar, so a long could be tested with the
     short branch the moment bias flipped. Direction is now captured at entry
     in positionIsLong.
  2. Stop-priority tie-break when both stop and target are touched in one bar
     (fleet convention; the original left it ambiguous).
  3. IsOverlay = false. Probability (0-100) and Bias (-100..100) were being
     plotted on the price axis at ~20,000, where they are invisible.
  4. Removed the stray "}V" character and both duplicated members.

NOT CHANGED - a known asymmetry left intact deliberately:
  meanReversionScore has a floor of 50 and only ever adds, so it can only feed
  bullishFactors, never bearishFactors. In backtest this made the strategy
  100% long (n=2005, zero shorts). That is arguably a bug, but fixing it
  CHANGES WHAT THE STRATEGY DOES, so it is a design decision, not a repair.
  See the backtest note at the bottom of this file.
"""

from pathlib import Path

OUT = Path(__file__).with_name("NQ_HybridEdge.cs")

CS = r'''#region Using declarations
using System;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Windows.Media;
using System.Xml.Serialization;
using NinjaTrader.Gui;
using NinjaTrader.Gui.Chart;
using NinjaTrader.Data;
using NinjaTrader.NinjaScript;
using NinjaTrader.NinjaScript.DrawingTools;
#endregion

namespace NinjaTrader.NinjaScript.Indicators
{
    /// <summary>
    /// NQ Hybrid Edge v2.0 - six independent edge factors combined into a
    /// probability score and a directional bias.
    /// INDICATOR ONLY - draws and scores, never submits an order.
    /// </summary>
    public class NQ_HybridEdge : Indicator
    {
        public enum TimezoneMode { Eastern, Pacific, UTC }

        #region Fields

        private double meanReversionScore;
        private double momentumScore;
        private double volumeProfileScore;
        private double volatilityScore;
        private double sessionTimeScore;
        private double statisticalScore;
        private double hybridProbability;
        private double directionalBias;
        private double volatilityRegime;

        private Bollinger bollinger;
        private RSI rsi;
        private MACD macd;
        private ATR atr;
        private SMA volumeSma;

        private double sessionHigh;
        private double sessionLow;
        private double sessionRange;
        private DateTime lastDate;

        private int barsSinceSignal;
        private int dailySignals;

        private bool isInPosition;
        private bool positionIsLong;
        private double stopLoss;
        private double profitTarget;

        #endregion

        #region Properties

        [NinjaScriptProperty]
        [Display(Name = "Timezone Mode", Description = "Timezone the chart clock reports", Order = 1, GroupName = "Session")]
        public TimezoneMode SessionTimezone { get; set; }

        [NinjaScriptProperty]
        [Range(2, int.MaxValue)]
        [Display(Name = "Bollinger Period", Order = 1, GroupName = "Inputs")]
        public int BollingerPeriod { get; set; }

        [NinjaScriptProperty]
        [Range(0.1, 5.0)]
        [Display(Name = "Bollinger StdDev", Order = 2, GroupName = "Inputs")]
        public double BollingerStdDev { get; set; }

        [NinjaScriptProperty]
        [Range(2, int.MaxValue)]
        [Display(Name = "RSI Period", Order = 3, GroupName = "Inputs")]
        public int RsiPeriod { get; set; }

        [NinjaScriptProperty]
        [Range(2, int.MaxValue)]
        [Display(Name = "ATR Period", Order = 4, GroupName = "Inputs")]
        public int AtrPeriod { get; set; }

        [NinjaScriptProperty]
        [Range(2, int.MaxValue)]
        [Display(Name = "Volume SMA Period", Order = 5, GroupName = "Inputs")]
        public int VolumeSmaPeriod { get; set; }

        [NinjaScriptProperty]
        [Range(0.0, 100.0)]
        [Display(Name = "Entry Threshold", Description = "Minimum hybrid probability to arm a signal", Order = 1, GroupName = "Signal")]
        public double EntryThreshold { get; set; }

        [NinjaScriptProperty]
        [Range(0.0, 100.0)]
        [Display(Name = "Bias Cutoff", Description = "Minimum absolute directional bias", Order = 2, GroupName = "Signal")]
        public double BiasCutoff { get; set; }

        [NinjaScriptProperty]
        [Range(0.1, 20.0)]
        [Display(Name = "Stop ATR Multiple", Order = 3, GroupName = "Signal")]
        public double StopAtrMultiple { get; set; }

        [NinjaScriptProperty]
        [Range(0.1, 20.0)]
        [Display(Name = "Target ATR Multiple", Order = 4, GroupName = "Signal")]
        public double TargetAtrMultiple { get; set; }

        [NinjaScriptProperty]
        [Range(0, int.MaxValue)]
        [Display(Name = "Signal Cooldown", Order = 5, GroupName = "Signal")]
        public int SignalCooldown { get; set; }

        [NinjaScriptProperty]
        [Range(1, int.MaxValue)]
        [Display(Name = "Max Daily Signals", Order = 6, GroupName = "Signal")]
        public int MaxDailySignals { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show Dashboard", Order = 1, GroupName = "Display")]
        public bool ShowDashboard { get; set; }

        [Browsable(false)]
        [XmlIgnore]
        public Series<double> Probability { get { return Values[0]; } }

        [Browsable(false)]
        [XmlIgnore]
        public Series<double> Bias { get { return Values[1]; } }

        [XmlIgnore]
        [Display(Name = "Hybrid Probability", Order = 1, GroupName = "Output")]
        public double HybridProbabilityValue { get { return hybridProbability; } }

        [XmlIgnore]
        [Display(Name = "Directional Bias", Order = 2, GroupName = "Output")]
        public double DirectionalBiasValue { get { return directionalBias; } }

        [XmlIgnore]
        [Display(Name = "Mean Reversion", Order = 3, GroupName = "Output")]
        public double MeanReversionScore { get { return meanReversionScore; } }

        [XmlIgnore]
        [Display(Name = "Momentum", Order = 4, GroupName = "Output")]
        public double MomentumScore { get { return momentumScore; } }

        [XmlIgnore]
        [Display(Name = "Volume Profile", Order = 5, GroupName = "Output")]
        public double VolumeProfileScore { get { return volumeProfileScore; } }

        [XmlIgnore]
        [Display(Name = "Volatility", Order = 6, GroupName = "Output")]
        public double VolatilityScore { get { return volatilityScore; } }

        [XmlIgnore]
        [Display(Name = "Session Time", Order = 7, GroupName = "Output")]
        public double SessionTimeScore { get { return sessionTimeScore; } }

        [XmlIgnore]
        [Display(Name = "Statistical", Order = 8, GroupName = "Output")]
        public double StatisticalScore { get { return statisticalScore; } }

        [XmlIgnore]
        [Display(Name = "Volatility Regime", Order = 9, GroupName = "Output")]
        public double VolatilityRegime { get { return volatilityRegime; } }

        #endregion

        #region State

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Description = "NQ Hybrid Edge v2.0 - multi-factor probability. Indicator only.";
                Name = "NQ_HybridEdge";
                Calculate = Calculate.OnBarClose;
                IsOverlay = false;
                DisplayInDataBox = true;
                DrawOnPricePanel = false;
                PaintPriceMarkers = false;
                ScaleJustification = ScaleJustification.Right;
                IsSuspendedWhileInactive = false;

                SessionTimezone = TimezoneMode.Eastern;
                BollingerPeriod = 20;
                BollingerStdDev = 2.0;
                RsiPeriod = 14;
                AtrPeriod = 14;
                VolumeSmaPeriod = 20;
                EntryThreshold = 65;
                BiasCutoff = 30;
                StopAtrMultiple = 1.5;
                TargetAtrMultiple = 3.0;
                SignalCooldown = 6;
                MaxDailySignals = 5;
                ShowDashboard = true;

                AddPlot(new Stroke(Brushes.DodgerBlue, 2), PlotStyle.Line, "Probability");
                AddPlot(new Stroke(Brushes.Orange, 2), PlotStyle.Line, "Bias");
            }
            else if (State == State.DataLoaded)
            {
                bollinger = Bollinger(BollingerStdDev, BollingerPeriod);
                rsi = RSI(RsiPeriod, 1);
                macd = MACD(12, 26, 9);
                atr = ATR(AtrPeriod);
                volumeSma = SMA(Volume, VolumeSmaPeriod);

                sessionHigh = double.MinValue;
                sessionLow = double.MaxValue;
                sessionRange = 0;
                lastDate = DateTime.MinValue;
                barsSinceSignal = SignalCooldown;
                dailySignals = 0;
                isInPosition = false;
                positionIsLong = false;
            }
        }

        #endregion

        #region OnBarUpdate

        protected override void OnBarUpdate()
        {
            if (CurrentBar < 60)
                return;

            UpdateSessionTracking();

            CalculateMeanReversionEdge();
            CalculateMomentumEdge();
            CalculateVolumeProfileEdge();
            CalculateVolatilityEdge();
            CalculateSessionTimeEdge();
            CalculateStatisticalEdge();
            CalculateHybridProbability();

            EvaluateSignal();

            Probability[0] = hybridProbability;
            Bias[0] = directionalBias;

            if (ShowDashboard)
                DrawDashboard();
        }

        #endregion

        #region Session tracking

        private void UpdateSessionTracking()
        {
            DateTime barTime = Time[0];

            if (barTime.Date != lastDate)
            {
                lastDate = barTime.Date;
                sessionHigh = High[0];
                sessionLow = Low[0];
                sessionRange = 0;
                dailySignals = 0;
            }

            sessionHigh = Math.Max(sessionHigh, High[0]);
            sessionLow = Math.Min(sessionLow, Low[0]);
            sessionRange = sessionHigh - sessionLow;

            if (barsSinceSignal < SignalCooldown)
                barsSinceSignal++;
        }

        #endregion

        #region Edge factor 1 - mean reversion

        private void CalculateMeanReversionEdge()
        {
            double score = 50;

            double bbUpper = bollinger.Upper[0];
            double bbLower = bollinger.Lower[0];
            double bbWidth = bbUpper - bbLower;

            if (bbWidth > 0)
            {
                double bbPosition = (Close[0] - bbLower) / bbWidth;

                if (bbPosition >= 0.95)
                    score = 70 + (bbPosition - 0.95) * 200;
                else if (bbPosition <= 0.05)
                    score = 70 + (0.05 - bbPosition) * 200;
                else if (bbPosition >= 0.8)
                    score = 60 + (bbPosition - 0.8) * 66.67;
                else if (bbPosition <= 0.2)
                    score = 60 + (0.2 - bbPosition) * 66.67;

                score = Math.Min(95, score);
            }

            double rsiValue = rsi[0];
            if (rsiValue >= 70 || rsiValue <= 30)
                score += 10;
            else if (rsiValue >= 60 || rsiValue <= 40)
                score += 5;

            double bbWidthAvg = 0;
            for (int i = 0; i < 20; i++)
                bbWidthAvg += bollinger.Upper[i] - bollinger.Lower[i];
            bbWidthAvg /= 20;

            if (bbWidthAvg > 0)
            {
                if (bbWidth < bbWidthAvg * 0.70)
                    score += 15;
                else if (bbWidth < bbWidthAvg * 0.85)
                    score += 10;
            }

            meanReversionScore = Clamp(score);
        }

        #endregion

        #region Edge factor 2 - momentum

        private void CalculateMomentumEdge()
        {
            double score;

            double macdHist = macd[0] - macd.Avg[0];
            double macdHistPrev = macd[1] - macd.Avg[1];

            if (macdHist > 0 && macdHistPrev <= 0)
                score = 75;
            else if (macdHist < 0 && macdHistPrev >= 0)
                score = 25;
            else if (macdHist > 0 && macdHist > macdHistPrev)
                score = 65;
            else if (macdHist < 0 && macdHist < macdHistPrev)
                score = 35;
            else if (macdHist > 0)
                score = 60;
            else
                score = 40;

            if (Close[5] > 0)
            {
                double roc5 = (Close[0] - Close[5]) / Close[5] * 100;
                if (roc5 > 0.5)
                    score += 5;
                else if (roc5 < -0.5)
                    score -= 5;
            }

            int upBars = 0;
            int downBars = 0;
            for (int i = 0; i < 5; i++)
            {
                if (Close[i] > Open[i])
                    upBars++;
                else if (Close[i] < Open[i])
                    downBars++;
            }

            if (upBars >= 4)
                score += 10;
            else if (downBars >= 4)
                score -= 10;

            momentumScore = Clamp(score);
        }

        #endregion

        #region Edge factor 3 - volume profile

        private void CalculateVolumeProfileEdge()
        {
            double score = 50;

            if (volumeSma[0] > 0)
            {
                double relVolume = Volume[0] / volumeSma[0];

                if (relVolume >= 2.0)
                    score = Close[0] > Open[0] ? 70 : 30;
                else if (relVolume >= 1.5)
                    score = Close[0] > Open[0] ? 65 : 35;
                else if (relVolume <= 0.5)
                    score = 55;

                if (Close[0] > Close[1] && Volume[0] > Volume[1])
                    score += 10;
                else if (Close[0] < Close[1] && Volume[0] > Volume[1])
                    score -= 10;
            }

            volumeProfileScore = Clamp(score);
        }

        #endregion

        #region Edge factor 4 - volatility

        private void CalculateVolatilityEdge()
        {
            double score = 50;

            double atrAvg = 0;
            for (int i = 0; i < 20; i++)
                atrAvg += atr[i];
            atrAvg /= 20;

            if (atrAvg > 0)
            {
                double atrRatio = atr[0] / atrAvg;

                if (atrRatio >= 1.5)
                {
                    score = 80;
                    volatilityRegime = 2;
                }
                else if (atrRatio >= 1.2)
                {
                    score = 60;
                    volatilityRegime = 1;
                }
                else if (atrRatio <= 0.7)
                {
                    score = 65;
                    volatilityRegime = -1;
                }
                else if (atrRatio <= 0.85)
                {
                    score = 55;
                    volatilityRegime = -0.5;
                }
                else
                {
                    score = 50;
                    volatilityRegime = 0;
                }
            }

            double currentRange = High[0] - Low[0];
            double avgRange = 0;
            for (int i = 0; i < 10; i++)
                avgRange += High[i] - Low[i];
            avgRange /= 10;

            if (avgRange > 0)
            {
                if (currentRange > avgRange * 1.5)
                    score += 10;
                else if (currentRange < avgRange * 0.5)
                    score -= 5;
            }

            volatilityScore = Clamp(score);
        }

        #endregion

        #region Edge factor 5 - session time

        private void CalculateSessionTimeEdge()
        {
            double score = 50;

            DateTime barTime = Time[0];
            int hour = barTime.Hour;
            int minute = barTime.Minute;

            if (SessionTimezone == TimezoneMode.Pacific)
                hour = (hour + 3) % 24;
            else if (SessionTimezone == TimezoneMode.UTC)
                hour = (hour + 20) % 24;

            int timeValue = hour * 100 + minute;

            if (timeValue >= 1500 && timeValue < 1530)
                score = 65;
            else if (timeValue >= 300 && timeValue < 330)
                score = 70;
            else if (timeValue >= 930 && timeValue < 1000)
                score = 75;
            else if (timeValue >= 1600 && timeValue < 2000)
                score = 55;
            else if (timeValue >= 400 && timeValue < 700)
                score = 60;
            else if (timeValue >= 1030 && timeValue < 1400)
                score = 65;
            else if (timeValue >= 1200 && timeValue < 1230)
                score = 70;
            else if (timeValue >= 800 && timeValue < 930)
                score = 65;
            else if (timeValue >= 100 && timeValue < 300)
                score = 40;
            else if (timeValue >= 1400 && timeValue < 1500)
                score = 45;

            if (sessionRange > 0)
            {
                double rangePosition = (Close[0] - sessionLow) / sessionRange;
                if (rangePosition >= 0.8 || rangePosition <= 0.2)
                    score += 10;
                else if (rangePosition >= 0.4 && rangePosition <= 0.6)
                    score -= 5;
            }

            sessionTimeScore = Clamp(score);
        }

        #endregion

        #region Edge factor 6 - statistical

        private void CalculateStatisticalEdge()
        {
            double score = 50;

            bool insideBar = High[1] <= High[2] && Low[1] >= Low[2];
            if (insideBar)
            {
                if (Close[0] > High[1])
                    score = 70;
                else if (Close[0] < Low[1])
                    score = 30;
            }

            bool bullishEngulfing = Close[1] < Open[1] && Close[0] > Open[0]
                                    && Close[0] > Open[1] && Open[0] < Close[1];
            bool bearishEngulfing = Close[1] > Open[1] && Close[0] < Open[0]
                                    && Open[0] > Close[1] && Close[0] < Open[1];

            if (bullishEngulfing)
                score = 75;
            else if (bearishEngulfing)
                score = 25;

            double bodySize = Math.Abs(Close[0] - Open[0]);
            double upperWick = High[0] - Math.Max(Close[0], Open[0]);
            double lowerWick = Math.Min(Close[0], Open[0]) - Low[0];

            if (lowerWick > bodySize * 2 && upperWick < bodySize * 0.5)
                score = 70;
            else if (upperWick > bodySize * 2 && lowerWick < bodySize * 0.5)
                score = 30;

            double totalRange = High[0] - Low[0];
            if (totalRange > 0 && bodySize < totalRange * 0.1)
                score = 50;

            int consecutiveUp = 0;
            int consecutiveDown = 0;
            for (int i = 0; i < 5; i++)
            {
                if (Close[i] > Open[i])
                    consecutiveUp++;
                else if (Close[i] < Open[i])
                    consecutiveDown++;
            }

            if (consecutiveUp >= 4)
                score += 5;
            else if (consecutiveDown >= 4)
                score -= 5;

            statisticalScore = Clamp(score);
        }

        #endregion

        #region Hybrid probability

        private void CalculateHybridProbability()
        {
            double weightMR = 0.20;
            double weightMom = 0.20;
            double weightVol = 0.15;
            double weightVola = 0.15;
            double weightST = 0.15;
            double weightStat = 0.15;

            if (volatilityRegime >= 1.5)
            {
                weightMR = 0.15; weightMom = 0.25; weightVol = 0.15;
                weightVola = 0.20; weightST = 0.10; weightStat = 0.15;
            }
            else if (volatilityRegime <= -0.5)
            {
                weightMR = 0.25; weightMom = 0.15; weightVol = 0.15;
                weightVola = 0.10; weightST = 0.15; weightStat = 0.20;
            }

            hybridProbability = (meanReversionScore * weightMR)
                              + (momentumScore * weightMom)
                              + (volumeProfileScore * weightVol)
                              + (volatilityScore * weightVola)
                              + (sessionTimeScore * weightST)
                              + (statisticalScore * weightStat);

            double bullishFactors = 0;
            double bearishFactors = 0;

            AccumulateBias(meanReversionScore, ref bullishFactors, ref bearishFactors);
            AccumulateBias(momentumScore, ref bullishFactors, ref bearishFactors);
            AccumulateBias(volumeProfileScore, ref bullishFactors, ref bearishFactors);
            AccumulateBias(statisticalScore, ref bullishFactors, ref bearishFactors);

            double totalBias = bullishFactors + bearishFactors;
            directionalBias = totalBias > 0
                ? (bullishFactors - bearishFactors) / totalBias * 100
                : 0;
        }

        private void AccumulateBias(double score, ref double bullish, ref double bearish)
        {
            if (score > 55)
                bullish += score - 50;
            else if (score < 45)
                bearish += 50 - score;
        }

        #endregion

        #region Signal evaluation - INDICATOR ONLY, never submits an order

        private void EvaluateSignal()
        {
            if (isInPosition)
            {
                CheckExit();
                return;
            }

            if (hybridProbability < EntryThreshold)
                return;
            if (barsSinceSignal < SignalCooldown)
                return;
            if (dailySignals >= MaxDailySignals)
                return;

            double risk = atr[0] * StopAtrMultiple;
            if (risk <= 0)
                return;

            if (directionalBias > BiasCutoff)
            {
                positionIsLong = true;
                stopLoss = Close[0] - risk;
                profitTarget = Close[0] + atr[0] * TargetAtrMultiple;
            }
            else if (directionalBias < -BiasCutoff)
            {
                positionIsLong = false;
                stopLoss = Close[0] + risk;
                profitTarget = Close[0] - atr[0] * TargetAtrMultiple;
            }
            else
            {
                return;
            }

            isInPosition = true;
            barsSinceSignal = 0;
            dailySignals++;

            Draw.ArrowUp(this, "sig" + CurrentBar, true, 0, Low[0] - TickSize * 4,
                positionIsLong ? Brushes.LimeGreen : Brushes.Transparent);
            if (!positionIsLong)
                Draw.ArrowDown(this, "sigD" + CurrentBar, true, 0, High[0] + TickSize * 4,
                    Brushes.Crimson);
        }

        private void CheckExit()
        {
            bool hitStop;
            bool hitTarget;

            if (positionIsLong)
            {
                hitStop = Low[0] <= stopLoss;
                hitTarget = High[0] >= profitTarget;
            }
            else
            {
                hitStop = High[0] >= stopLoss;
                hitTarget = Low[0] <= profitTarget;
            }

            if (hitStop)
                isInPosition = false;
            else if (hitTarget)
                isInPosition = false;
        }

        #endregion

        #region Drawing

        private void DrawDashboard()
        {
            string text = string.Format(
                "NQ HYBRID EDGE v2.0   INDICATOR ONLY\n"
                + "Probability {0,6:F1}   Bias {1,7:F1}\n"
                + "------------------------------------\n"
                + "MeanRev {2,5:F0}    Momentum    {3,5:F0}\n"
                + "Volume  {4,5:F0}    Volatility  {5,5:F0}\n"
                + "Session {6,5:F0}    Statistical {7,5:F0}\n"
                + "Regime  {8,5:F1}    Signals today {9}\n"
                + "In position: {10}",
                hybridProbability, directionalBias,
                meanReversionScore, momentumScore,
                volumeProfileScore, volatilityScore,
                sessionTimeScore, statisticalScore,
                volatilityRegime, dailySignals,
                isInPosition ? (positionIsLong ? "LONG" : "SHORT") : "flat");

            Draw.TextFixed(this, "NQHybridEdgeDash", text, TextPosition.TopRight,
                Brushes.White, new SimpleFont("Consolas", 12), Brushes.Transparent,
                Brushes.MidnightBlue, 85);
        }

        #endregion

        #region Helpers

        private double Clamp(double value)
        {
            return Math.Min(100, Math.Max(0, value));
        }

        #endregion
    }
}
'''


def verify(text):
    """Catch the exact class of fault that broke build.py and create.py."""
    problems = []

    if text.count("{") != text.count("}"):
        problems.append("brace mismatch: {} open vs {} close".format(
            text.count("{"), text.count("}")))

    import re
    depth = 0
    for n, line in enumerate(text.split("\n"), 1):
        code = re.sub(r"//.*", "", line)
        if re.match(r"\s*(private|protected|public)\s+(override\s+)?"
                    r"(void|double|bool|int|string|Series<double>)\s+\w+\(", code):
            if depth != 2:
                problems.append("line {}: method declared at depth {} (expected 2)".format(n, depth))
        depth += code.count("{") - code.count("}")
    if depth != 0:
        problems.append("file ends at depth {} (expected 0)".format(depth))

    # Count DECLARATIONS only - a bare "Name()" also matches call sites, which
    # is legitimate (OnBarUpdate calls CalculateHybridProbability once).
    decls = re.findall(r"^\s*(?:private|protected|public)\s+(?:override\s+)?"
                       r"(?:void|double|bool|int|string|Series<double>)\s+(\w+)\s*\(",
                       text, re.M)
    for name in set(decls):
        if decls.count(name) > 1:
            problems.append("{} DECLARED {} times - duplicate member".format(name, decls.count(name)))

    return problems


if __name__ == "__main__":
    OUT.write_text(CS, encoding="utf-8")
    print("wrote {}  ({:,} bytes, {:,} lines)".format(OUT.name, len(CS), CS.count("\n") + 1))

    issues = verify(CS)
    if issues:
        print("\nVERIFICATION FAILED:")
        for p in issues:
            print("  - " + p)
        raise SystemExit(1)

    print("verification passed: braces balanced, no method misnested, no duplicate members")
    print("\nBACKTEST NOTE (2026-09-07, 15-min NQ, 5.7 years, n=2005):")
    print("  net +0.062 R/trade, win 36.1%, t=1.93, p(1t)=0.0269 vs zero")
    print("  BUT vs a random-long control with the same bracket: z=+1.78, p~0.10")
    print("  and excl_top5% = -0.039. Every trade was LONG - see the header note")
    print("  on the meanReversionScore asymmetry. Not validated; chart use only.")
