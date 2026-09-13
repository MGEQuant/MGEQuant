#region Using declarations
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

