#!/usr/bin/env python3
"""Create the NQ Hybrid Edge Indicator v2.0"""

content = '''#region Using declarations
using System;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Windows.Media;
using System.Xml.Serialization;
using NinjaTrader.NinjaScript;
using NinjaTrader.NinjaScript.DrawingTools;

namespace NinjaTrader.NinjaScript.Indicators
{
    /// <summary>
    /// NQ Hybrid Edge Indicator v2.0
    /// A multi-factor probability indicator for NQ/MNQ.
    /// Combines 6 independent edge factors with adaptive weighting.
    /// Includes backtestable strategy definition with entry/exit rules.
    /// </summary>
    public class NQ_HybridEdge : Indicator
    {
        #region Enums
        public enum TimezoneMode
        {
            Eastern,
            Pacific,
            UTC
        }
        #endregion

        #region Private Fields

        // Edge factor scores (0-100 each)
        private double meanReversionScore;
        private double momentumScore;
        private double volumeProfileScore;
        private double volatilityScore;
        private double sessionTimeScore;
        private double statisticalScore;

        // Combined probability
        private double hybridProbability;
        private double directionalBias;

        // Indicators
        private Indicator.Bollinger bollinger;
        private Indicator.RSI rsi;
        private Indicator.MACD macd;
        private Indicator.ATR atr;
        private Indicator.SMA volumeSma;

        // Tracking
        private double volatilityRegime;

        // Session tracking
        private double sessionHigh;
        private double sessionLow;
        private double sessionRange;
        private DateTime lastDate;

        // Signal management
        private int barsSinceSignal;
        private int dailySignals;

        // Strategy state
        private bool isInPosition;
        private double stopLoss;
        private double profitTarget;

        #endregion

        #region Properties

        [NinjaScriptProperty]
        [Display(Name = "Timezone Mode", Description = "Timezone for session detection", Order = 1, GroupName = "Session")]
        public TimezoneMode SessionTimezone { get; set; }

        [NinjaScriptProperty]
        [Range(1, int.MaxValue)]
        [Display(Name = "Bollinger Period", Order = 1, GroupName = "Mean Reversion")]
        public int BollingerPeriod { get; set; }

        [NinjaScriptProperty]
        [Range(0.1, 5.0)]
        [Display(Name = "Bollinger StdDev", Order = 2, GroupName = "Mean Reversion")]
        public double BollingerStdDev { get; set; }

        [NinjaScriptProperty]
        [Range(1, int.MaxValue)]
        [Display(Name = "RSI Period", Order = 1, GroupName = "Momentum")]
        public int RsiPeriod { get; set; }

        [NinjaScriptProperty]
        [Range(1, int.MaxValue)]
        [Display(Name = "ATR Period", Order = 1, GroupName = "Volatility")]
        public int AtrPeriod { get; set; }

        [NinjaScriptProperty]
        [Range(1, int.MaxValue)]
        [Display(Name = "Volume SMA Period", Order = 1, GroupName = "Volume")]
        public int VolumeSmaPeriod { get; set; }

        [NinjaScriptProperty]
        [Range(0, 100)]
        [Display(Name = "Entry Threshold", Description = "Min probability to enter", Order = 1, GroupName = "Strategy")]
        public int EntryThreshold { get; set; }

        [NinjaScriptProperty]
        [Range(0.1, 10.0)]
        [Display(Name = "Stop ATR Multiple", Description = "Stop loss in ATR multiples", Order = 2, GroupName = "Strategy")]
        public double StopAtrMultiple { get; set; }

        [NinjaScriptProperty]
        [Range(0.1, 20.0)]
        [Display(Name = "Target ATR Multiple", Description = "Profit target in ATR multiples", Order = 3, GroupName = "Strategy")]
        public double TargetAtrMultiple { get; set; }

        [NinjaScriptProperty]
        [Range(1, int.MaxValue)]
        [Display(Name = "Signal Cooldown", Order = 1, GroupName = "Signal Management")]
        public int SignalCooldown { get; set; }

        [NinjaScriptProperty]
        [Range(1, int.MaxValue)]
        [Display(Name = "Max Daily Signals", Order = 2, GroupName = "Signal Management")]
        public int MaxDailySignals { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show Dashboard", Order = 1, GroupName = "Display")]
        public bool ShowDashboard { get; set; }

        // Output properties
        [XmlIgnore]
        [Display(Name = "Hybrid Probability", Order = 1, GroupName = "Output")]
        public double HybridProbability => hybridProbability;

        [XmlIgnore]
        [Display(Name = "Direction Bias", Order = 2, GroupName = "Output")]
        public double DirectionBias => directionalBias;

        [XmlIgnore]
        [Display(Name = "Mean Reversion", Order = 1, GroupName = "Edge Factors")]
        public double MeanReversionScore => meanReversionScore;

        [XmlIgnore]
        [Display(Name = "Momentum", Order = 2, GroupName = "Edge Factors")]
        public double MomentumScore => momentumScore;

        [XmlIgnore]
        [Display(Name = "Volume Profile", Order = 3, GroupName = "Edge Factors")]
        public double VolumeProfileScore => volumeProfileScore;

        [XmlIgnore]
        [Display(Name = "Volatility", Order = 4, GroupName = "Edge Factors")]
        public double VolatilityScore => volatilityScore;

        [XmlIgnore]
        [Display(Name = "Session Time", Order = 5, GroupName = "Edge Factors")]
        public double SessionTimeScore => sessionTimeScore;

        [XmlIgnore]
        [Display(Name = "Statistical", Order = 6, GroupName = "Edge Factors")]
        public double StatisticalScore => statisticalScore;

        [XmlIgnore]
        [Display(Name = "Volatility Regime", Order = 7, GroupName = "Edge Factors")]
        public double VolatilityRegime => volatilityRegime;

        #endregion

        #region Initialize

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Description = "NQ Hybrid Edge v2.0 - Multi-Factor Probability Indicator";
                Name = "NQ_HybridEdge";
                Calculate = Calculate.OnBarClose;
                IsOverlay = true;
                DisplayInDataBox = true;
                DrawOnPricePanel = true;
                PaintPriceMarkers = false;
                ScaleJustification = ScaleJustification.Right;
                IsSuspendedWhileInactive = false;

                // Defaults
                SessionTimezone = TimezoneMode.Eastern;
                BollingerPeriod = 20;
                BollingerStdDev = 2.0;
                RsiPeriod = 14;
                AtrPeriod = 14;
                VolumeSmaPeriod = 20;
                EntryThreshold = 65;
                StopAtrMultiple = 1.5;
                TargetAtrMultiple = 3.0;
                SignalCooldown = 6;
                MaxDailySignals = 5;
                ShowDashboard = true;

                // Plots
                AddPlot(new Stroke(Brushes.DodgerBlue, 2), PlotStyle.Line, "Probability");
                AddPlot(new Stroke(Brushes.Orange, 2), PlotStyle.Line, "Bias");
            }
            else if (State == State.DataLoaded)
            {
                bollinger = Bollinger(BollingerStdDev, BollingerPeriod);
                rsi = RSI(RsiPeriod);
                macd = MACD(12, 26, 9);
                atr = ATR(AtrPeriod);
                volumeSma = SMA(VolumeSmaPeriod);

                sessionHigh = double.MinValue;
                sessionLow = double.MaxValue;
                lastDate = DateTime.MinValue;
                barsSinceSignal = SignalCooldown;
                dailySignals = 0;
                isInPosition = false;
            }
        }

        #endregion

        #region OnBarUpdate

        protected override void OnBarUpdate()
        {
            if (CurrentBar < 50)
                return;

            UpdateSessionTracking();
            CalculateMeanReversionEdge();
            CalculateMomentumEdge();
            CalculateVolumeProfileEdge();
            CalculateVolatilityEdge();
            CalculateSessionTimeEdge();
            CalculateStatisticalEdge();
            CalculateHybridProbability();
            ExecuteStrategy();

            Probability[0] = hybridProbability;
            Bias[0] = directionalBias;

            if (ShowDashboard)
                DrawDashboard();
        }

        #endregion

        #region Session Tracking

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

        #region Edge Factor 1: Mean Reversion

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

            // RSI confirmation
            double rsiValue = rsi[0];
            if (rsiValue >= 70 || rsiValue <= 30)
                score += 10;
            else if (rsiValue >= 60 || rsiValue <= 40)
                score += 5;

            // Band width squeeze
            double bbWidthAvg = 0;
            for (int i = 0; i < 20; i++)
                bbWidthAvg += (bollinger.Upper[i] - bollinger.Lower[i]);
            bbWidthAvg /= 20;

            if (bbWidth < bbWidthAvg * 0.7)
                score += 15;
            else if (bbWidth < bbWidthAvg * 0.85)
                score += 10;

            meanReversionScore = Math.Min(100, Math.Max(0, score));
        }

        #endregion

        #region Edge Factor 2: Momentum

        private void CalculateMomentumEdge()
        {
            double score = 50;

            double macdValue = macd[0];
            double macdSignal = macd.Avg[0];
            double macdHist = macdValue - macdSignal;

            double macdPrev = macd[1];
            double macdSignalPrev = macd.Avg[1];
            double macdHistPrev = macdPrev - macdSignalPrev;

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

            // Rate of change
            if (Close[5] > 0)
            {
                double roc5 = (Close[0] - Close[5]) / Close[5] * 100;
                if (roc5 > 0.5)
                    score += 5;
                else if (roc5 < -0.5)
                    score -= 5;
            }

            // Consecutive directional bars
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

            momentumScore = Math.Min(100, Math.Max(0, score));
        }

        #endregion

        #region Edge Factor 3: Volume Profile

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

                // Volume-price confirmation
                if (Close[0] > Close[1] && Volume[0] > Volume[1])
                    score += 10;
                else if (Close[0] < Close[1] && Volume[0] > Volume[1])
                    score -= 10;
            }

            volumeProfileScore = Math.Min(100, Math.Max(0, score));
        }

        #endregion

        #region Edge Factor 4: Volatility

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
                    score = 70;
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

            // Bar range analysis
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

            volatilityScore = Math.Min(100, Math.Max(0, score));
        }

        #endregion

        #region Edge Factor 5: Session Time

        private void CalculateSessionTimeEdge()
        {
            double score = 50;

            DateTime barTime = Time[0];
            int hour = barTime.Hour;
            int minute = barTime.Minute;

            // Convert to Eastern Time if needed
            if (SessionTimezone == TimezoneMode.Pacific)
                hour = (hour + 2) % 24; // PT to ET
            else if (SessionTimezone == TimezoneMode.UTC)
                hour = (hour + 4) % 24; // UTC to ET (approximate)

            int timeValue = hour * 100 + minute;

            // Opening ranges (first 30 min)
            if (timeValue >= 1500 && timeValue < 1530)
                score = 65; // Asia open (3:00 PM ET)
            else if (timeValue >= 300 && timeValue < 330)
                score = 70; // London open (3:00 AM ET)
            else if (timeValue >= 930 && timeValue < 1000)
                score = 75; // NY open (9:30 AM ET)
            // Mid-session
            else if (timeValue >= 1600 && timeValue < 2000)
                score = 55;
            else if (timeValue >= 400 && timeValue < 700)
                score = 60;
            else if (timeValue >= 1030 && timeValue < 1400)
                score = 65;
            // Session transitions
            else if (timeValue >= 1200 && timeValue < 1230)
                score = 70; // Asia-London overlap
            else if (timeValue >= 800 && timeValue < 930)
                score = 65; // London-NY overlap
            // Low probability times
            else if (timeValue >= 100 && timeValue < 300)
                score = 40;
            else if (timeValue >= 1400 && timeValue < 1500)
                score = 45;

            // Session range position
            if (sessionRange > 0)
            {
                double rangePosition = (Close[0] - sessionLow) / sessionRange;
                if (rangePosition >= 0.8 || rangePosition <= 0.2)
                    score += 10;
                else if (rangePosition >= 0.4 && rangePosition <= 0.6)
                    score -= 5;
            }

            sessionTimeScore = Math.Min(100, Math.Max(0, score));
        }

        #endregion

        #region Edge Factor 6: Statistical

        private void CalculateStatisticalEdge()
        {
            double score = 50;

            // Inside bar breakout
            bool insideBar = High[1] <= High[2] && Low[1] >= Low[2];
            if (insideBar)
            {
                if (Close[0] > High[1])
                    score = 70;
                else if (Close[0] < Low[1])
                    score = 30;
            }

            // Engulfing
            bool bullishEngulfing = Close[1] < Open[1] && Close[0] > Open[0] &&
                                    Close[0] > Open[1] && Open[0] < Close[1];
            bool bearishEngulfing = Close[1] > Open[1] && Close[0] < Open[0] &&
                                    Open[0] > Close[1] && Close[0] < Open[1];

            if (bullishEngulfing)
                score = 75;
            else if (bearishEngulfing)
                score = 25;

            // Pin bar
            double bodySize = Math.Abs(Close[0] - Open[0]);
            double upperWick = High[0] - Math.Max(Close[0], Open[0]);
            double lowerWick = Math.Min(Close[0], Open[0]) - Low[0];

            if (lowerWick > bodySize * 2 && upperWick < bodySize * 0.5)
                score = 70;
            else if (upperWick > bodySize * 2 && lowerWick < bodySize * 0.5)
                score = 30;

            // Doji
            double totalRange = High[0] - Low[0];
            if (totalRange > 0 && bodySize < totalRange * 0.1)
                score = 50;

            // Consecutive pattern
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

            statisticalScore = Math.Min(100, Math.Max(0, score));
        }

        #endregion

        #region Hybrid Probability Calculation

        private void CalculateHybridProbability()
        {
            // Base weights
            double weightMR = 0.20;
            double weightMom = 0.20;
            double weightVol = 0.15;
            double weightVola = 0.15;
            double weightST = 0.15;
            double weightStat = 0.15;

            // Adjust weights based on volatility regime
            if (volatilityRegime >= 1.5)
            {
                weightMR = 0.15;
                weightMom = 0.25;
                weightVol = 0.15;
                weightVola = 0.20;
                weightST = 0.10;
                weightStat = 0.15;
            }
            else if (volatilityRegime <= -0.5)
            {
                weightMR = 0.25;
                weightMom = 0.15;
                weightVol = 0.15;
                weightVola = 0.10;
                weightST = 0.15;
                weightStat = 0.20;
            }

            // Weighted probability
            hybridProbability = (meanReversionScore * weightMR) +
                               (momentumScore * weightMom) +
                               (volumeProfileScore * weightVol) +
                               (volatilityScore * weightVola) +
                               (sessionTimeScore * weightST) +
                               (statisticalScore * weightStat);

            // Directional bias
            double bullishFactors = 0;
            double bearishFactors = 0;

            if (meanReversionScore > 55) bullishFactors += meanReversionScore - 50;
            if (meanReversionScore < 45) bearishFactors += 50 - meanReversionScore;
            if (momentumScore > 55) bullishFactors += momentumScore - 50;
            if (momentumScore < 45) bearishFactors += 50 - momentumScore;
            if (volumeProfileScore > 55) bullishFactors += volumeProfileScore - 50;
            if (volumeProfileScore < 45) bearishFactors += 50 - volumeProfileScore;
            if (statisticalScore > 55) bullishFactors += statisticalScore - 50;
            if (statisticalScore < 45) bearishFactors += 50 - statisticalScore;

            double totalBias = bullishFactors + bearishFactors;
            directionalBias = totalBias > 0 ? (bullishFactors - bearishFactors) / totalBias * 100 : 0;
        }

        #endregion

        #region Strategy Execution

        private void ExecuteStrategy()
        {
            // Check for exit if in position
            if (isInPosition)
            {
                CheckExit();
                return;
            }

            // Check for entry
            if (hybridProbability < EntryThreshold)
                return;

            if (barsSinceSignal < SignalCooldown)
                return;

            if (dailySignals >= MaxDailySignals)
                return;

            // Enter long
            if (directionalBias > 30)
            {
                stopLoss = Close[0] - atr[0] * StopAtrMultiple;
                profitTarget = Close[0] + atr[0] * TargetAtrMultiple;
                isInPosition = true;
                barsSinceSignal = 0;
                dailySignals++;
            }
            // Enter short
            else if (directionalBias < -30)
            {
                stopLoss = Close[0] + atr[0] * StopAtrMultiple;
                profitTarget = Close[0] - atr[0] * TargetAtrMultiple;
                isInPosition = true;
                barsSinceSignal = 0;
                dailySignals++;
            }
        }

        private void CheckExit()
        {
            // Long position
            if (directionalBias > 0)
            {
                if (Low[0] <= stopLoss || High[0] >= profitTarget)
                    isInPosition = false;
            }
            // Short position
            else
            {
                if (High[0] >= stopLoss || Low[0] <= profitTarget)
                    isInPosition = false;
            }
        }

        #endregion

        #region Drawing

        private void DrawDashboard()
        {
            if (CurrentBar < 1)
                return;

            double yPosition = High[0] + (High[0] - Low[0]) * 0.5;

            string dashboardText = string.Format(
                "NQ Hybrid: {0:F1}% | Bias: {1:F0} | MR:{2} M:{3} V:{4} Vol:{5} S:{6} St:{7}",
                hybridProbability,
                directionalBias,
                meanReversionScore.ToString("F0"),
                momentumScore.ToString("F0"),
                volumeProfileScore.ToString("F0"),
                volatilityScore.ToString("F0"),
                sessionTimeScore.ToString("F0"),
                statisticalScore.ToString("F0")
            );

            Brush textBrush = hybridProbability >= 70 ? Brushes.LimeGreen :
                              hybridProbability >= 55 ? Brushes.Yellow :
                              hybridProbability >= 45 ? Brushes.Orange : Brushes.Red;

            Draw.Text(this, "Dashboard", true, dashboardText, 0, yPosition, 0,
                textBrush, new SimpleFont("Arial", 9), TextAlignment.Center,
                Brushes.Transparent, Brushes.Transparent, 0);
        }

        #endregion
    }
}
'''

with open(r'f:\Trading Software\MGEQuant\Releases\NQ_ProbabilityIndicator\NQ_HybridEdge.cs', 'w') as f:
    f.write(content)

print("File created successfully!")
