#region Using declarations
using System;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using NinjaTrader.Cbi;
using NinjaTrader.Data;
using NinjaTrader.NinjaScript;
using NinjaTrader.NinjaScript.Strategies;
#endregion

namespace NinjaTrader.NinjaScript.Strategies
{
    // Research-only: NY opening displacement, then retest/reclaim continuation.
    // This intentionally does not take the raw first opening-range break.
    public class NqNyOpeningDisplacementRetestResearch : Strategy
    {
        [NinjaScriptProperty]
        [Range(1, 10)]
        [Display(Name = "Quantity", Order = 1, GroupName = "Safety")]
        public int Quantity { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Required Account Name Contains", Order = 2, GroupName = "Safety")]
        public string RequiredAccountNameContains { get; set; }

        [NinjaScriptProperty]
        [Range(1, 10000)]
        [Display(Name = "Maximum Dollar Risk", Order = 3, GroupName = "Safety")]
        public double MaximumDollarRisk { get; set; }

        [NinjaScriptProperty]
        [Range(1, 10000)]
        [Display(Name = "Daily Loss Limit", Order = 4, GroupName = "Safety")]
        public double DailyLossLimit { get; set; }

        private TimeZoneInfo eastern;
        private DateTime sessionKey = DateTime.MinValue;
        private double sessionStartProfit;
        private double rangeHigh = double.MinValue, rangeLow = double.MaxValue;
        private bool rangeDefined, tradedToday, displacementSeen;
        private bool displacementLong;
        private int displacementBar;
        private double brokenEdge;
        private double pointValue;
        private bool symbolAllowed;

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Name = "NqNyOpeningDisplacementRetestResearch";
                Description = "RESEARCH ONLY. NQ/MNQ 5-minute NY opening displacement plus retest continuation; no live approval implied.";
                Calculate = Calculate.OnBarClose;
                EntriesPerDirection = 1;
                EntryHandling = EntryHandling.AllEntries;
                IsExitOnSessionCloseStrategy = true;
                ExitOnSessionCloseSeconds = 300;
                StartBehavior = StartBehavior.WaitUntilFlat;
                RealtimeErrorHandling = RealtimeErrorHandling.StopCancelClose;
                StopTargetHandling = StopTargetHandling.PerEntryExecution;
                IsFillLimitOnTouch = false;
                Slippage = 1;
                BarsRequiredToTrade = 20;
                IsInstantiatedOnEachOptimizationIteration = true;
                Quantity = 1;
                RequiredAccountNameContains = string.Empty;
                MaximumDollarRisk = 250;
                DailyLossLimit = 500;
            }
            else if (State == State.Configure)
            {
                AddDataSeries(BarsPeriodType.Minute, 1);
            }
            else if (State == State.DataLoaded)
            {
                pointValue = Instrument.MasterInstrument.PointValue;
                string master = Instrument.MasterInstrument.Name;
                symbolAllowed = (master == "NQ" || master == "MNQ")
                    && BarsPeriod.BarsPeriodType == BarsPeriodType.Minute && BarsPeriod.Value == 5;
                eastern = TimeZoneInfo.FindSystemTimeZoneById("Eastern Standard Time");
                sessionStartProfit = SystemPerformance.AllTrades.TradesPerformance.Currency.CumProfit;
            }
        }

        protected override void OnBarUpdate()
        {
            DateTime et = ToEastern(Time[0]);
            if (BarsInProgress == 1)
            {
                if (Position.MarketPosition != MarketPosition.Flat && et.Hour == 16 && et.Minute >= 55)
                {
                    ExitLong("EOD", "NYODR_LONG");
                    ExitShort("EOD", "NYODR_SHORT");
                }
                return;
            }
            if (CurrentBar < BarsRequiredToTrade || !symbolAllowed)
                return;
            string actual = Account == null ? string.Empty : Account.Name;
            if (string.IsNullOrEmpty(RequiredAccountNameContains) || actual.IndexOf(RequiredAccountNameContains, StringComparison.OrdinalIgnoreCase) < 0)
                return;
            DateTime key = et.Hour < 17 ? et.Date.AddDays(-1) : et.Date;
            if (key != sessionKey)
            {
                sessionKey = key; rangeHigh = double.MinValue; rangeLow = double.MaxValue;
                rangeDefined = false; tradedToday = false; displacementSeen = false;
                sessionStartProfit = SystemPerformance.AllTrades.TradesPerformance.Currency.CumProfit;
            }
            if (Position.MarketPosition != MarketPosition.Flat)
                return;
            if (SystemPerformance.AllTrades.TradesPerformance.Currency.CumProfit - sessionStartProfit <= -DailyLossLimit || tradedToday)
                return;
            int minute = et.Hour * 60 + et.Minute;
            if (minute >= 570 && minute < 585)
            {
                rangeHigh = Math.Max(rangeHigh, High[0]); rangeLow = Math.Min(rangeLow, Low[0]); return;
            }
            if (minute == 585 && rangeHigh > double.MinValue)
                rangeDefined = true;
            if (!rangeDefined || minute < 585 || minute >= 630)
                return;
            if (!displacementSeen)
            {
                double atr = ATR(14)[0];
                double threshold = Math.Max(4 * TickSize, 0.50 * atr);
                double body = Close[0] - Open[0];
                double barRange = High[0] - Low[0];
                if (CurrentBar - 1 >= 0 && body >= threshold && Close[0] > rangeHigh && Close[0] >= Low[0] + 0.75 * barRange)
                { displacementSeen = true; displacementLong = true; displacementBar = CurrentBar; brokenEdge = rangeHigh; return; }
                if (body <= -threshold && Close[0] < rangeLow && Close[0] <= High[0] - 0.75 * barRange)
                { displacementSeen = true; displacementLong = false; displacementBar = CurrentBar; brokenEdge = rangeLow; return; }
            }
            if (!displacementSeen || CurrentBar - displacementBar > 6)
            { displacementSeen = false; return; }
            bool retest = displacementLong
                ? Low[0] <= brokenEdge && Close[0] > brokenEdge && Close[0] > Open[0]
                : High[0] >= brokenEdge && Close[0] < brokenEdge && Close[0] < Open[0];
            if (!retest)
                return;
            double entry = Close[0];
            double stop = displacementLong
                ? Math.Min(Low[0], brokenEdge) - 2 * TickSize
                : Math.Max(High[0], brokenEdge) + 2 * TickSize;
            int stopTicks = Math.Max(1, (int)Math.Round(Math.Abs(entry - stop) / TickSize));
            if (stopTicks < 4 || stopTicks > 50 || stopTicks * TickSize * pointValue * Quantity > MaximumDollarRisk)
                return;
            string signal = displacementLong ? "NYODR_LONG" : "NYODR_SHORT";
            SetStopLoss(signal, CalculationMode.Price, stop, false);
            SetProfitTarget(signal, CalculationMode.Price, displacementLong ? entry + stopTicks * TickSize : entry - stopTicks * TickSize);
            if (displacementLong) EnterLong(Quantity, signal); else EnterShort(Quantity, signal);
            tradedToday = true; displacementSeen = false;
        }

        private DateTime ToEastern(DateTime timestamp)
        {
            return TimeZoneInfo.ConvertTime(timestamp, eastern);
        }
    }
}
