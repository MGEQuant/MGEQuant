#region Using declarations
using System;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using NinjaTrader.Cbi;
using NinjaTrader.NinjaScript;
using NinjaTrader.NinjaScript.Strategies;
#endregion

namespace NinjaTrader.NinjaScript.Strategies
{
    // Research-only: a failed expansion from a compressed 5-minute cluster.
    public class NqCompressionSnapbackResearch : Strategy
    {
        private DateTime sessionKey = DateTime.MinValue;
        private double sessionStartProfit;
        private int tradesThisSession;
        private int lastEntryBar = -100000;
        private double pointValue;
        private bool symbolAllowed;

        [NinjaScriptProperty]
        [Range(1, 10)]
        [Display(Name = "Quantity", Order = 1, GroupName = "Risk")]
        public int Quantity { get; set; }

        [NinjaScriptProperty]
        [Range(1.0, 10000.0)]
        [Display(Name = "Maximum Dollar Risk", Order = 2, GroupName = "Risk")]
        public double MaximumDollarRisk { get; set; }

        [NinjaScriptProperty]
        [Range(1.0, 10000.0)]
        [Display(Name = "Daily Loss Limit", Order = 3, GroupName = "Risk")]
        public double DailyLossLimit { get; set; }

        [NinjaScriptProperty]
        [Range(1, 10)]
        [Display(Name = "Maximum Trades Per Session", Order = 4, GroupName = "Risk")]
        public int MaximumTradesPerSession { get; set; }

        [NinjaScriptProperty]
        [Range(0, 100)]
        [Display(Name = "Cooldown Bars", Order = 5, GroupName = "Risk")]
        public int CooldownBars { get; set; }

        [NinjaScriptProperty]
        [Range(2, 10)]
        [Display(Name = "Compression Bars", Order = 1, GroupName = "Setup")]
        public int CompressionBars { get; set; }

        [NinjaScriptProperty]
        [Range(5, 100)]
        [Display(Name = "Reference Cluster Count", Order = 2, GroupName = "Setup")]
        public int ReferenceClusterCount { get; set; }

        [NinjaScriptProperty]
        [Range(0.10, 1.0)]
        [Display(Name = "Compression Factor", Order = 3, GroupName = "Setup")]
        public double CompressionFactor { get; set; }

        [NinjaScriptProperty]
        [Range(1, 20)]
        [Display(Name = "Probe Ticks", Order = 4, GroupName = "Setup")]
        public int ProbeTicks { get; set; }

        [NinjaScriptProperty]
        [Range(1, 20)]
        [Display(Name = "Stop Buffer Ticks", Order = 5, GroupName = "Setup")]
        public int StopBufferTicks { get; set; }

        [NinjaScriptProperty]
        [Range(1, 200)]
        [Display(Name = "Maximum Stop Ticks", Order = 6, GroupName = "Setup")]
        public int MaximumStopTicks { get; set; }

        [NinjaScriptProperty]
        [Range(17, 23)]
        [Display(Name = "Electronic Start Hour ET", Order = 1, GroupName = "Session")]
        public int ElectronicStartHour { get; set; }

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Name = "NqCompressionSnapbackResearch";
                Description = "RESEARCH ONLY. Fixed 1:1 NQ/MNQ compression snapback; no live approval implied.";
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
                BarsRequiredToTrade = 30;
                IsInstantiatedOnEachOptimizationIteration = true;

                Quantity = 1;
                MaximumDollarRisk = 250;
                DailyLossLimit = 500;
                MaximumTradesPerSession = 2;
                CooldownBars = 6;

                CompressionBars = 3;
                ReferenceClusterCount = 20;
                CompressionFactor = 0.75;
                ProbeTicks = 2;
                StopBufferTicks = 2;
                MaximumStopTicks = 48;
                ElectronicStartHour = 18;
            }
            else if (State == State.DataLoaded)
            {
                pointValue = Instrument.MasterInstrument.PointValue;
                string master = Instrument.MasterInstrument.Name;
                symbolAllowed = master == "NQ" || master == "MNQ";
                sessionStartProfit = SystemPerformance.AllTrades.TradesPerformance.Currency.CumProfit;
            }
        }

        protected override void OnBarUpdate()
        {
            if (BarsInProgress != 0 || CurrentBar < ReferenceClusterCount + CompressionBars + 2)
                return;

            DateTime et = ToEastern(Time[0]);
            DateTime currentSession = et.Hour < 17 ? et.Date.AddDays(-1) : et.Date;
            if (currentSession != sessionKey)
            {
                sessionKey = currentSession;
                sessionStartProfit = SystemPerformance.AllTrades.TradesPerformance.Currency.CumProfit;
                tradesThisSession = 0;
            }

            if (!symbolAllowed || !IsElectronicMinute(et) || et.Hour == 17)
                return;

            if (Position.MarketPosition != MarketPosition.Flat)
            {
                if (et.Hour == 16 && et.Minute >= 55)
                    ExitLong("EOD", "CS_LONG");
                if (et.Hour == 16 && et.Minute >= 55)
                    ExitShort("EOD", "CS_SHORT");
                return;
            }

            double realizedSinceSessionStart = SystemPerformance.AllTrades.TradesPerformance.Currency.CumProfit - sessionStartProfit;
            if (realizedSinceSessionStart <= -DailyLossLimit || tradesThisSession >= MaximumTradesPerSession
                || CurrentBar - lastEntryBar <= CooldownBars)
                return;

            double clusterHigh = double.MinValue;
            double clusterLow = double.MaxValue;
            double clusterWidth = 0;
            for (int barsAgo = 1; barsAgo <= CompressionBars; barsAgo++)
            {
                clusterHigh = Math.Max(clusterHigh, High[barsAgo]);
                clusterLow = Math.Min(clusterLow, Low[barsAgo]);
            }
            clusterWidth = clusterHigh - clusterLow;

            double[] widths = new double[ReferenceClusterCount];
            for (int block = 0; block < ReferenceClusterCount; block++)
            {
                double high = double.MinValue;
                double low = double.MaxValue;
                int firstBarsAgo = CompressionBars + 1 + block * CompressionBars;
                for (int barsAgo = firstBarsAgo; barsAgo < firstBarsAgo + CompressionBars; barsAgo++)
                {
                    high = Math.Max(high, High[barsAgo]);
                    low = Math.Min(low, Low[barsAgo]);
                }
                widths[block] = high - low;
            }
            Array.Sort(widths);
            double medianWidth = widths[ReferenceClusterCount / 2];
            if (medianWidth <= 0 || clusterWidth > CompressionFactor * medianWidth)
                return;

            bool failedHigh = High[0] >= clusterHigh + ProbeTicks * TickSize
                && Close[0] < clusterHigh && Close[0] > clusterLow;
            bool failedLow = Low[0] <= clusterLow - ProbeTicks * TickSize
                && Close[0] < clusterHigh && Close[0] > clusterLow;
            if (!failedHigh && !failedLow)
                return;

            bool goShort = failedHigh;
            double stopPrice = goShort ? High[0] + StopBufferTicks * TickSize : Low[0] - StopBufferTicks * TickSize;
            double entryReference = Close[0];
            int stopTicks = Math.Max(1, (int)Math.Round(Math.Abs(entryReference - stopPrice) / TickSize));
            double dollarRisk = stopTicks * TickSize * pointValue * Quantity;
            if (stopTicks > MaximumStopTicks || dollarRisk > MaximumDollarRisk)
                return;

            SetStopLoss(goShort ? "CS_SHORT" : "CS_LONG", CalculationMode.Ticks, stopTicks, false);
            SetProfitTarget(goShort ? "CS_SHORT" : "CS_LONG", CalculationMode.Ticks, stopTicks);
            if (goShort)
                EnterShort(Quantity, "CS_SHORT");
            else
                EnterLong(Quantity, "CS_LONG");
            tradesThisSession++;
            lastEntryBar = CurrentBar;
        }

        private bool IsElectronicMinute(DateTime et)
        {
            int minute = et.Hour * 60 + et.Minute;
            return minute >= ElectronicStartHour * 60 || minute < 17 * 60;
        }

        private DateTime ToEastern(DateTime timestamp)
        {
            try
            {
                TimeZoneInfo eastern = TimeZoneInfo.FindSystemTimeZoneById("Eastern Standard Time");
                return TimeZoneInfo.ConvertTime(timestamp, eastern);
            }
            catch
            {
                return timestamp;
            }
        }
    }
}
