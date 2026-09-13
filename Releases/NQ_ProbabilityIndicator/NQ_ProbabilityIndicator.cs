#region Using declarations
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Linq;
using System.Text;
using System.Windows;
using System.Windows.Media;
using System.Xml.Serialization;
using NinjaTrader.Cbi;
using NinjaTrader.Gui;
using NinjaTrader.Gui.Chart;
using NinjaTrader.Gui.Tools;
using NinjaTrader.Data;
using NinjaTrader.NinjaScript;
using NinjaTrader.NinjaScript.DrawingTools;
using NinjaTrader.Core;

namespace NinjaTrader.NinjaScript.Indicators
{
    /// <summary>
    /// NQ Hybrid Probability Indicator
    /// A completely new probability-based trading indicator for NQ/MNQ
    /// Combines 6 independent edge factors:
    /// 1. Mean Reversion Edge
    /// 2. Momentum Edge
    /// 3. Volume Profile Edge
    /// 4. Volatility Edge
    /// 5. Time/Session Edge
    /// 6. Statistical Edge
    /// </summary>
    public class NQ_ProbabilityIndicator : Indicator
    {
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
        private double directionalBias; // -100 to +100

        // Indicators
        private Indicator.Bollinger bollinger;
        private Indicator.RSI rsi;
        private Indicator.MACD macd;
        private Indicator.ATR atr;
        private Indicator.VolumeIndicator volume;

        // Tracking
        private double atrAverage;
        private double volumeAverage;
        private double priceRateOfChange;
        private double volatilityRegime;
        private int consecutiveDirectionalBars;

        // Session tracking
        private double sessionOpen;
        private double sessionHigh;
        private double sessionLow;
        private double sessionRange;
        private DateTime lastDate;

        // Signal management
        private int barsSinceSignal;
        private int dailySignals;

        #endregion

        #region Properties

        [NinjaScriptProperty]
        [Range(1, int.MaxValue)]
        [Display(Name = "Bollinger Period", Description = "Bollinger Band period", Order = 1, GroupName = "Mean Reversion")]
        public int BollingerPeriod { get; set; }

        [NinjaScriptProperty]
        [Range(0.1, 5.0)]
        [Display(Name = "Bollinger StdDev", Description = "Bollinger Band standard deviations", Order = 2, GroupName = "Mean Reversion")]
        public double BollingerStdDev { get; set; }

        [NinjaScriptProperty]
        [Range(1, int.MaxValue)]
        [Display(Name = "RSI Period", Description = "RSI period", Order = 1, GroupName = "Momentum")]
        public int RsiPeriod { get; set; }

        [NinjaScriptProperty]
        [Range(1, int.MaxValue)]
        [Display(Name = "MACD Fast", Description = "MACD fast period", Order = 2, GroupName = "Momentum")]
        public int MacdFast { get; set; }

        [NinjaScriptProperty]
        [Range(1, int.MaxValue)]
        [Display(Name = "MACD Slow", Description = "MACD slow period", Order = 3, GroupName = "Momentum")]
        public int MacdSlow { get; set; }

        [NinjaScriptProperty]
        [Range(1, int.MaxValue)]
        [Display(Name = "ATR Period", Description = "ATR period for volatility", Order = 1, GroupName = "Volatility")]
        public int AtrPeriod { get; set; }

        [NinjaScriptProperty]
        [Range(1, int.MaxValue)]
        [Display(Name = "Volume Average Period", Description = "Volume average lookback", Order = 1, GroupName = "Volume")]
        public int VolumeAvgPeriod { get; set; }

        [NinjaScriptProperty]
        [Range(1, int.MaxValue)]
        [Display(Name = "Signal Cooldown", Description = "Bars between signals", Order = 1, GroupName = "Signal Management")]
        public int SignalCooldown { get; set; }

        [NinjaScriptProperty]
        [Range(1, int.MaxValue)]
        [Display(Name = "Max Daily Signals", Description = "Maximum signals per day", Order = 2, GroupName = "Signal Management")]
        public int MaxDailySignals { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show Dashboard", Description = "Show probability dashboard", Order = 1, GroupName = "Display")]
        public bool ShowDashboard { get; set; }

        // Output properties
        [XmlIgnore]
        [Display(Name = "Hybrid Probability", Description = "Combined probability score (0-100)", Order = 1, GroupName = "Output")]
        public double HybridProbability
        { get { return hybridProbability; } }

        [XmlIgnore]
        [Display(Name = "Direction Bias", Description = "Directional bias (-100 to +100)", Order = 2, GroupName = "Output")]
        public double DirectionBias
        { get { return directionalBias; } }

        [XmlIgnore]
        [Display(Name = "Mean Reversion", Description = "Mean reversion edge score", Order = 1, GroupName = "Edge Factors")]
        public double MeanReversionScore
        { get { return meanReversionScore; } }

        [XmlIgnore]
        [Display(Name = "Momentum", Description = "Momentum edge score", Order = 2, GroupName = "Edge Factors")]
        public double MomentumScore
        { get { return momentumScore; } }

        [XmlIgnore]
        [Display(Name = "Volume Profile", Description = "Volume profile edge score", Order = 3, GroupName = "Edge Factors")]
        public double VolumeProfileScore
        { get { return volumeProfileScore; } }

        [XmlIgnore]
        [Display(Name = "Volatility", Description = "Volatility edge score", Order = 4, GroupName = "Edge Factors")]
        public double VolatilityScore
        { get { return volatilityScore; } }

        [XmlIgnore]
        [Display(Name = "Session Time", Description = "Session time edge score", Order = 5, GroupName = "Edge Factors")]
        public double SessionTimeScore
        { get { return sessionTimeScore; } }

        [XmlIgnore]
        [Display(Name = "Statistical", Description = "Statistical edge score", Order = 6, GroupName = "Edge Factors")]
        public double StatisticalScore
        { get { return statisticalScore; } }

        #endregion

        #region Initialize

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Description = "NQ Hybrid Probability Indicator - Multi-Factor Edge Detection";
                Name = "NQ_ProbabilityIndicator";
                Calculate = Calculate.OnBarClose;
                IsOverlay = true;
                DisplayInDataBox = true;
                DrawOnPricePanel = true;
                PaintPriceMarkers = false;
                ScaleJustification = ScaleJustification.Right;
                IsSuspendedWhileInactive = false;

                // Default parameters
                BollingerPeriod = 20;
                BollingerStdDev = 2.0;
                RsiPeriod = 14;
                MacdFast = 12;
                MacdSlow = 26;
                AtrPeriod = 14;
                VolumeAvgPeriod = 20;
                SignalCooldown = 6;
                MaxDailySignals = 8;
                ShowDashboard = true;

                // Add plot series
                AddPlot(new Stroke(Brushes.DodgerBlue, 2), PlotStyle.Line, "Probability");
                AddPlot(new Stroke(Brushes.Orange, 2), PlotStyle.Line, "Bias");
            }
            else if (State == State.DataLoaded)
            {
                // Initialize indicators
                bollinger = Bollinger(BollingerStdDev, BollingerPeriod);
                rsi = RSI(RsiPeriod);
                macd = MACD(MacdFast, MacdSlow, 9);
                atr = ATR(AtrPeriod);
                volume = Volume(VolumeAvgPeriod);

                // Initialize tracking
                sessionHigh = double.MinValue;
                sessionLow = double.MaxValue;
                lastDate = DateTime.MinValue;
                barsSinceSignal = SignalCooldown;
                dailySignals = 0;
            }
        }

        #endregion

        #region OnBarUpdate

        protected override void OnBarUpdate()
        {
            if (CurrentBar < 50)
                return;

            // Update session tracking
            UpdateSessionTracking();

            // Calculate each independent edge factor
            CalculateMeanReversionEdge();
            CalculateMomentumEdge();
            CalculateVolumeProfileEdge();
            CalculateVolatilityEdge();
            CalculateSessionTimeEdge();
            CalculateStatisticalEdge();

            // Combine all edges into hybrid probability
            CalculateHybridProbability();

            // Update plots
            Probability[0] = hybridProbability;
            Bias[0] = directionalBias;

            // Draw dashboard
            if (ShowDashboard)
                DrawDashboard();
        }

        #endregion

        #region Session Tracking

        private void UpdateSessionTracking()
        {
            DateTime barTime = Time[0];

            // New day reset
            if (barTime.Date != lastDate)
            {
                lastDate = barTime.Date;
                sessionHigh = High[0];
                sessionLow = Low[0];
                sessionOpen = Open[0];
                sessionRange = 0;
                dailySignals = 0;
            }

            // Update session metrics
            sessionHigh = Math.Max(sessionHigh, High[0]);
            sessionLow = Math.Min(sessionLow, Low[0]);
            sessionRange = sessionHigh - sessionLow;

            // Update signal cooldown
            if (barsSinceSignal < SignalCooldown)
                barsSinceSignal++;
        }

        #endregion

        #region Edge Factor 1: Mean Reversion

        private void CalculateMeanReversionEdge()
        {
            double score = 50; // Neutral starting point

            // Bollinger Band position
            double bbUpper = bollinger.Upper[0];
            double bbLower = bollinger.Lower[0];
            double bbMiddle = bollinger.Middle[0];
            double bbWidth = bbUpper - bbLower;

            // Price position within bands
            double bbPosition = (Close[0] - bbLower) / bbWidth;

            // Extreme readings indicate mean reversion opportunity
            if (bbPosition >= 0.95)
            {
                // Price at upper band - bearish mean reversion
                score = 70 + (bbPosition - 0.95) * 200;
                score = Math.Min(95, score);
            }
            else if (bbPosition <= 0.05)
            {
                // Price at lower band - bullish mean reversion
                score = 70 + (0.05 - bbPosition) * 200;
                score = Math.Min(95, score);
            }
            else if (bbPosition >= 0.8)
            {
                score = 60 + (bbPosition - 0.8) * 66.67;
            }
            else if (bbPosition <= 0.2)
            {
                score = 60 + (0.2 - bbPosition) * 66.67;
            }
            else
            {
                score = 50;
            }

            // RSI confirmation
            double rsiValue = rsi[0];
            if (rsiValue >= 70)
                score += 10;
            else if (rsiValue <= 30)
                score += 10;
            else if (rsiValue >= 60 || rsiValue <= 40)
                score += 5;

            // Band width contraction (squeeze) increases mean reversion probability
            double bbWidthAvg = 0;
            for (int i = 0; i < 20; i++)
                bbWidthAvg += (bollinger.Upper[i] - bollinger.Lower[i]);
            bbWidthAvg /= 20;

            if (bbWidth < bbWidthAvg * 0.7)
                score += 15; // Tight squeeze
            else if (bbWidth < bbWidthAvg * 0.85)
                score += 10;

            meanReversionScore = Math.Min(100, Math.Max(0, score));
        }

        #endregion

        #region Edge Factor 2: Momentum

        private void CalculateMomentumEdge()
        {
            double score = 50;

            // MACD signal
            double macdValue = macd[0];
            double macdSignal = macd.Avg[0];
            double macdHist = macdValue - macdSignal;

            // MACD crossover
            double macdPrev = macd[1];
            double macdSignalPrev = macd.Avg[1];
            double macdHistPrev = macdPrev - macdSignalPrev;

            if (macdHist > 0 && macdHistPrev <= 0)
                score = 75; // Bullish crossover
            else if (macdHist < 0 && macdHistPrev >= 0)
                score = 25; // Bearish crossover
            else if (macdHist > 0 && macdHist > macdHistPrev)
                score = 65; // Bullish momentum increasing
            else if (macdHist < 0 && macdHist < macdHistPrev)
                score = 35; // Bearish momentum increasing
            else if (macdHist > 0)
                score = 60; // Bullish momentum
            else
                score = 40; // Bearish momentum

            // Rate of change
            double roc5 = (Close[0] - Close[5]) / Close[5] * 100;
            double roc10 = (Close[0] - Close[10]) / Close[10] * 100;

            if (roc5 > 0.5 && roc10 > 0.3)
                score += 10;
            else if (roc5 < -0.5 && roc10 < -0.3)
                score -= 10;

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

            // Relative volume
            double relVolume = Volume[0] / volume.Avg[0];

            if (relVolume >= 2.0)
            {
                // High volume climax
                if (Close[0] > Open[0])
                    score = 70; // Bullish volume climax
                else
                    score = 30; // Bearish volume climax
            }
            else if (relVolume >= 1.5)
            {
                if (Close[0] > Open[0])
                    score = 65;
                else
                    score = 35;
            }
            else if (relVolume <= 0.5)
            {
                // Low volume - potential reversal
                score = 55;
            }

            // Volume trend
            double volTrend = 0;
            for (int i = 0; i < 5; i++)
                volTrend += Volume[i];
            volTrend /= 5;

            double volAvgLong = 0;
            for (int i = 0; i < 20; i++)
                volAvgLong += Volume[i];
            volAvgLong /= 20;

            if (volTrend > volAvgLong * 1.3)
                score += 10; // Increasing volume
            else if (volTrend < volAvgLong * 0.7)
                score -= 5; // Decreasing volume

            // Volume-price confirmation
            if (Close[0] > Close[1] && Volume[0] > Volume[1])
                score += 10; // Bullish volume confirmation
            else if (Close[0] < Close[1] && Volume[0] > Volume[1])
                score -= 10; // Bearish volume confirmation

            volumeProfileScore = Math.Min(100, Math.Max(0, score));
        }

        #endregion

        #region Edge Factor 4: Volatility

        private void CalculateVolatilityEdge()
        {
            double score = 50;

            // ATR relative to average
            double atrAvg = 0;
            for (int i = 0; i < 20; i++)
                atrAvg += atr[i];
            atrAvg /= 20;

            double atrRatio = atr[0] / atrAvg;

            // Volatility regime
            if (atrRatio >= 1.5)
            {
                // High volatility - expansion phase
                score = 70;
                volatilityRegime = 2;
            }
            else if (atrRatio >= 1.2)
            {
                // Above average volatility
                score = 60;
                volatilityRegime = 1;
            }
            else if (atrRatio <= 0.7)
            {
                // Low volatility - contraction, breakout coming
                score = 65;
                volatilityRegime = -1;
            }
            else if (atrRatio <= 0.85)
            {
                // Below average volatility
                score = 55;
                volatilityRegime = -0.5;
            }
            else
            {
                score = 50;
                volatilityRegime = 0;
            }

            // ATR trend
            double atrTrend = atr[0] - atr[5];
            if (atrTrend > 0)
                score += 5; // Volatility increasing
            else
                score -= 5; // Volatility decreasing

            // Bar range analysis
            double currentRange = High[0] - Low[0];
            double avgRange = 0;
            for (int i = 0; i < 10; i++)
                avgRange += High[i] - Low[i];
            avgRange /= 10;

            if (currentRange > avgRange * 1.5)
                score += 10; // Large range bar
            else if (currentRange < avgRange * 0.5)
                score -= 5; // Small range bar

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
            int timeValue = hour * 100 + minute;

            // Session time analysis (Eastern Time)
            // Asia: 3:00 PM - 12:00 AM ET
            // London: 3:00 AM - 8:30 AM ET
            // New York: 9:30 AM - 4:00 PM ET

            // Opening ranges (first 30 min) - higher probability
            if (timeValue >= 1500 && timeValue < 1530)
                score = 65; // Asia open
            else if (timeValue >= 300 && timeValue < 330)
                score = 70; // London open
            else if (timeValue >= 930 && timeValue < 1000)
                score = 75; // NY open
            // Mid-session
            else if (timeValue >= 1600 && timeValue < 2000)
                score = 55; // Asia mid
            else if (timeValue >= 400 && timeValue < 700)
                score = 60; // London mid
            else if (timeValue >= 1030 && timeValue < 1400)
                score = 65; // NY mid
            // Session transitions
            else if (timeValue >= 1200 && timeValue < 1230)
                score = 70; // Asia-London overlap
            else if (timeValue >= 800 && timeValue < 930)
                score = 65; // London-NY overlap
            // Low probability times
            else if (timeValue >= 100 && timeValue < 300)
                score = 40; // Asia close
            else if (timeValue >= 1400 && timeValue < 1500)
                score = 45; // NY close
            else
                score = 50;

            // Session range position
            if (sessionRange > 0)
            {
                double rangePosition = (Close[0] - sessionLow) / sessionRange;
                if (rangePosition >= 0.8)
                    score += 10; // Near session high
                else if (rangePosition <= 0.2)
                    score += 10; // Near session low
                else if (rangePosition >= 0.4 && rangePosition <= 0.6)
                    score -= 5; // Middle of range
            }

            sessionTimeScore = Math.Min(100, Math.Max(0, score));
        }

        #endregion

        #region Edge Factor 6: Statistical

        private void CalculateStatisticalEdge()
        {
            double score = 50;

            // Win rate of similar setups (simplified)
            // Look at recent price action patterns

            // Pattern 1: Inside bar breakout
            bool insideBar = High[1] <= High[2] && Low[1] >= Low[2];
            if (insideBar)
            {
                if (Close[0] > High[1])
                {
                    score = 70; // Bullish inside bar breakout
                }
                else if (Close[0] < Low[1])
                {
                    score = 30; // Bearish inside bar breakout
                }
            }

            // Pattern 2: Engulfing
            bool bullishEngulfing = Close[1] < Open[1] && Close[0] > Open[0] &&
                                    Close[0] > Open[1] && Open[0] < Close[1];
            bool bearishEngulfing = Close[1] > Open[1] && Close[0] < Open[0] &&
                                    Open[0] > Close[1] && Close[0] < Open[1];

            if (bullishEngulfing)
                score = 75;
            else if (bearishEngulfing)
                score = 25;

            // Pattern 3: Pin bar
            double bodySize = Math.Abs(Close[0] - Open[0]);
            double upperWick = High[0] - Math.Max(Close[0], Open[0]);
            double lowerWick = Math.Min(Close[0], Open[0]) - Low[0];

            if (lowerWick > bodySize * 2 && upperWick < bodySize * 0.5)
                score = 70; // Bullish pin bar
            else if (upperWick > bodySize * 2 && lowerWick < bodySize * 0.5)
                score = 30; // Bearish pin bar

            // Pattern 3: Doji (indecision)
            if (bodySize < (High[0] - Low[0]) * 0.1)
                score = 50; // Doji - neutral

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
            // Weighted combination of all edge factors
            // Weights are designed to be adaptive based on market conditions

            double weightMR = 0.20;  // Mean Reversion
            double weightMom = 0.20; // Momentum
            double weightVol = 0.15;  // Volume Profile
            double weightVola = 0.15; // Volatility
            double weightST = 0.15;   // Session Time
            double weightStat = 0.15; // Statistical

            // Adjust weights based on volatility regime
            if (volatilityRegime >= 1.5)
            {
                // High volatility - favor momentum and volatility
                weightMR = 0.15;
                weightMom = 0.25;
                weightVol = 0.15;
                weightVola = 0.20;
                weightST = 0.10;
                weightStat = 0.15;
            }
            else if (volatilityRegime <= -0.5)
            {
                // Low volatility - favor mean reversion and statistical
                weightMR = 0.25;
                weightMom = 0.15;
                weightVol = 0.15;
                weightVola = 0.10;
                weightST = 0.15;
                weightStat = 0.20;
            }

            // Calculate weighted probability
            hybridProbability = (meanReversionScore * weightMR) +
                               (momentumScore * weightMom) +
                               (volumeProfileScore * weightVol) +
                               (volatilityScore * weightVola) +
                               (sessionTimeScore * weightST) +
                               (statisticalScore * weightStat);

            // Calculate directional bias
            // Positive = bullish, Negative = bearish
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
            if (totalBias > 0)
                directionalBias = (bullishFactors - bearishFactors) / totalBias * 100;
            else
                directionalBias = 0;

            // Signal management
            if (hybridProbability >= 70 && barsSinceSignal >= SignalCooldown && dailySignals < MaxDailySignals)
            {
                barsSinceSignal = 0;
                dailySignals++;
            }
        }

        #endregion

        #region Drawing

        private void DrawDashboard()
        {
            if (CurrentBar < 1)
                return;

            // Dashboard position
            double yPosition = High[0] + (High[0] - Low[0]) * 0.5;

            // Format dashboard text
            string dashboardText = string.Format(
                "NQ Hybrid Prob: {0:F1}% | Bias: {1:F0} | MR:{2} M:{3} V:{4} Vol:{5} S:{6} St:{7}",
                hybridProbability,
                directionalBias,
                meanReversionScore.ToString("F0"),
                momentumScore.ToString("F0"),
                volumeProfileScore.ToString("F0"),
                volatilityScore.ToString("F0"),
                sessionTimeScore.ToString("F0"),
                statisticalScore.ToString("F0")
            );

            // Color based on probability
            Brush textBrush = Brushes.White;
            if (hybridProbability >= 70)
                textBrush = Brushes.LimeGreen;
            else if (hybridProbability >= 55)
                textBrush = Brushes.Yellow;
            else if (hybridProbability >= 45)
                textBrush = Brushes.Orange;
            else
                textBrush = Brushes.Red;

            // Draw dashboard
            Draw.Text(this, "Dashboard", true, dashboardText, 0, yPosition, 0, textBrush, new SimpleFont("Arial", 9), TextAlignment.Center, Brushes.Transparent, Brushes.Transparent, 0);
        }

        #endregion
    }
}
