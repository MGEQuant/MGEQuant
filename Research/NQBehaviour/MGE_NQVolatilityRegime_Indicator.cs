#region Using declarations
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Windows.Media;
using System.Xml.Serialization;
using NinjaTrader.Data;
using NinjaTrader.Gui;
using NinjaTrader.Gui.Chart;
using NinjaTrader.Gui.Tools;
using NinjaTrader.NinjaScript;
using NinjaTrader.NinjaScript.DrawingTools;
#endregion

// =====================================================================================
// MGE NQ VOLATILITY REGIME - INDICATOR ONLY, PLACES NO ORDERS
// =====================================================================================
// WHAT THIS IS, AND WHAT IT DELIBERATELY IS NOT.
//
// Built 2026-09-02 from a data-first study of NQ (Research/NQBehaviour). That study
// measured NQ's own behaviour before proposing anything, and found:
//
//   RETURNS: null essentially everywhere. ~40 tests - drift by hour, overnight vs RTH,
//   autocorrelation from 5m to daily, day-of-week, conditional follow-through - produced
//   three marginal cells, two of which CONTRADICT each other (15m says momentum, 30m says
//   reversion, both at autocorr ~0.01). Nothing survives honest accounting. Notably the
//   published equity overnight-drift anomaly does NOT hold in NQ futures (t=0.36).
//
//   VOLATILITY: strong, clean, and stable. A 5x intraday swing in 5-minute true range.
//
// So this indicator makes NO directional claim. It does not print signals, arrows, or
// bias. Claiming direction is exactly what the data says cannot be supported, and it is
// what sank the ORB, session-open reversion, exhaustion fade, compression snapback,
// EMA-retest and ICT-levels efforts before it.
//
// WHAT IT DOES CLAIM, AND THE EVIDENCE:
//   Expected range = LEVEL (causal trailing median TR) x SHAPE (time-of-day profile).
//   The shape was fitted on TRAIN ONLY (2020-12..2023-12) and validated on 2024-2026,
//   untouched during exploration:
//       trailing level alone        MAE 43.05 ticks   R2 0.010   medAPE 45.3%
//       level x shape (this model)  MAE 36.30 ticks   R2 0.042   medAPE 36.1%
//   The shape adds R2 +0.032 and cuts median proportional error by 9.3 points OUT OF
//   SAMPLE. Shape stability vs the train profile: r = +0.997 (2024), +0.989 (2025),
//   +0.950 (2026). Unlike anything in the returns table, this persists.
//
// WHAT WAS TESTED AND REJECTED - do not re-add it:
//   Whether the regime ratio sorts MarketCoach's 168 long trades. Pre-specified
//   hypothesis was that abnormally hot conditions underperform. It was WRONG: the hot
//   quartile was the BEST (+0.487 excl_top5%) and the pattern is a non-monotonic U shape
//   (Q1 +0.338, Q2 -0.001, Q3 +0.002, Q4 +0.487), t=-1.87 with a CI including zero. So
//   this is NOT a trade filter and must not be used as one.
//
// WHY IT IS USEFUL ANYWAY: a fixed tick-based stop means wildly different things by hour.
// Compression Snapback applied the same 48-tick cap at every hour - that is 2.2x the
// normal 5-min range at midnight ET but 0.3x at 10:00, a 7x difference in meaning, and it
// placed 2,303 of its 2,312 trades overnight. MarketCoach's swing-based stop plus its
// ATR floor is the fleet's one volatility-aware sizing, and is plausibly part of why it
// is the one that works. This makes that adaptivity explicit and available to anything.
// =====================================================================================

namespace NinjaTrader.NinjaScript.Indicators
{
    // The user's directional choice. The indicator never sets this itself - it has no
    // directional opinion and the data says it should not pretend to.
    public enum MGEPlanDirection
    {
        Off,
        Long,
        Short,
        Both
    }

    public class MGE_NQVolatilityRegime_Indicator : Indicator
    {
        // Half-hour Eastern buckets, index 0 = 00:00-00:30 ET. Fitted on TRAIN only,
        // normalised so the median bucket is 1.0. Index 35 (17:30-18:00 ET) is the
        // maintenance halt and carries no data - it is flagged, never divided by.
        private static readonly double[] EasternShape = new double[]
        {
            0.5507, 0.5507, 0.6957, 0.7246, 0.9565, 0.8696, 1.3913, 1.2464,
            1.2754, 1.0725, 0.9855, 0.9855, 1.0145, 0.9565, 1.1014, 1.0725,
            1.2174, 1.5362, 1.3913, 3.8261, 3.4493, 2.8986, 2.5797, 2.2319,
            2.0580, 1.8841, 1.9710, 1.8551, 1.9710, 1.9710, 2.0580, 2.2029,
            1.3913, 0.6087, 0.6377, 0.0000, 0.9565, 0.6377, 0.6957, 0.6667,
            0.8986, 0.8116, 0.7826, 0.8406, 0.7246, 0.6377, 0.5797, 0.5507
        };

        private const int HaltBucket = 35;

        private readonly List<double> trueRangeTicks = new List<double>();
        private double cachedLevelTicks;
        private int lastLevelBar = -100000;
        private bool symbolWarned;

        // --- trade plan state ---------------------------------------------------------
        // Two modes. PlanAnchorPrice == 0 is PREVIEW: levels follow the current price and
        // nothing is tracked, because nothing is committed. PlanAnchorPrice > 0 is
        // COMMITTED: the plan freezes at that price and TP1/TP2/TP3/stop hits are tracked
        // from there, including the breakeven transition.
        private const string PlanTag = "MGEVR_PLAN";
        private bool planActive;
        private bool planIsLong;
        private bool planCommitted;
        private double planEntry, planStop, planRisk, planTp1, planTp2, planTp3;
        private double planAnchorUsed;
        private int planDirectionUsed;
        private int planStartBar;
        private bool planTp1Hit, planTp2Hit, planTp3Hit, planStopped;

        [NinjaScriptProperty]
        [Range(1, 120)]
        [Display(Name = "Level Lookback (sessions)", Order = 1, GroupName = "1. Model",
            Description = "Sessions of completed 5-minute bars used for the trailing median true range (the LEVEL). 20 matches the validated Python model.")]
        public int LookbackSessions { get; set; }

        [NinjaScriptProperty]
        [Range(-12, 12)]
        [Display(Name = "Platform-to-Eastern offset (hours)", Order = 2, GroupName = "1. Model",
            Description = "Hours to ADD to chart time to get Eastern. This platform is configured Pacific, so the default is 3. Check Tools > Options > General > Time zone if the ET clock below looks wrong.")]
        public int PlatformToEasternOffsetHours { get; set; }

        [NinjaScriptProperty]
        [Range(0.1, 10.0)]
        [Display(Name = "Stop = x normal range", Order = 3, GroupName = "2. Sizing",
            Description = "Multiple of the expected 5-minute range to suggest as a stop distance. A reference for sizing only - this indicator makes no directional claim.")]
        public double StopRangeMultiple { get; set; }

        [NinjaScriptProperty]
        [Range(1, 100000)]
        [Display(Name = "Risk budget per trade ($)", Order = 4, GroupName = "2. Sizing",
            Description = "Dollar risk used to convert the suggested stop distance into a contract count.")]
        public double RiskDollarsPerTrade { get; set; }

        [Display(Name = "Show dashboard", Order = 5, GroupName = "3. Display")]
        public bool ShowDashboard { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Plan direction", Order = 1, GroupName = "4. Trade Plan",
            Description = "Off draws nothing. Long or Short draws one bracket and can track it. Both draws the long and short brackets side by side so you can compare them before choosing - Both is always preview, since you cannot hold two opposite positions. This is YOUR directional choice; the indicator has no opinion and never suggests a side.")]
        public MGEPlanDirection PlanDirection { get; set; }

        [NinjaScriptProperty]
        [Range(0, 1000000)]
        [Display(Name = "Plan anchor price (0 = preview)", Order = 2, GroupName = "4. Trade Plan",
            Description = "0 = PREVIEW: levels follow the current price, nothing is tracked. Type your actual fill price to COMMIT: the plan freezes there and TP1/TP2/TP3/stop hits and the breakeven move are tracked from that price.")]
        public double PlanAnchorPrice { get; set; }

        [NinjaScriptProperty]
        [Range(0.1, 20.0)]
        [Display(Name = "TP1 (R multiple)", Order = 3, GroupName = "4. Trade Plan",
            Description = "First target in R. A 1.0R first target with a breakeven move after it is the only exit structure in this project that has actually been backtested; deeper targets are preference, not evidence.")]
        public double Target1R { get; set; }

        [NinjaScriptProperty]
        [Range(0.1, 20.0)]
        [Display(Name = "TP2 (R multiple)", Order = 4, GroupName = "4. Trade Plan")]
        public double Target2R { get; set; }

        [NinjaScriptProperty]
        [Range(0.1, 20.0)]
        [Display(Name = "TP3 runner (R multiple)", Order = 5, GroupName = "4. Trade Plan",
            Description = "Third leg. NOT covered by any backtest in this project - the tested structure is two legs. Treat as a preference, not a validated target.")]
        public double Target3R { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Move stop to breakeven at TP1", Order = 6, GroupName = "4. Trade Plan",
            Description = "Matches the tested two-leg model. It is not free: it converts some full winners into breakeven scratches, which is why an exit of this shape produces three outcomes (-1R, +0.5R, +1.5R) rather than two.")]
        public bool MoveToBreakevenAtTp1 { get; set; }

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Name = "MGE_NQVolatilityRegime_Indicator";
                Description = "INDICATOR ONLY. Expected 5-minute range = trailing level x validated time-of-day shape. Makes NO directional claim; explicitly not a trade filter.";
                Calculate = Calculate.OnBarClose;
                IsOverlay = false;
                DisplayInDataBox = true;
                // Plan levels are price levels, so drawing has to land on the price panel.
                DrawOnPricePanel = true;
                PaintPriceMarkers = true;
                IsSuspendedWhileInactive = true;

                LookbackSessions = 20;
                PlatformToEasternOffsetHours = 3;
                StopRangeMultiple = 1.5;
                RiskDollarsPerTrade = 250;
                ShowDashboard = true;

                PlanDirection = MGEPlanDirection.Off;
                PlanAnchorPrice = 0;
                Target1R = 1.0;
                Target2R = 2.0;
                Target3R = 3.0;
                MoveToBreakevenAtTp1 = true;

                AddPlot(new Stroke(Brushes.DeepSkyBlue, 2), PlotStyle.Line, "ExpectedRange");
                AddPlot(new Stroke(Brushes.Orange, 2), PlotStyle.Line, "ActualRange");
            }
            else if (State == State.Configure)
            {
                trueRangeTicks.Clear();
                cachedLevelTicks = 0;
                lastLevelBar = -100000;
            }
        }

        protected override void OnBarUpdate()
        {
            if (CurrentBar < 2)
                return;

            if (!symbolWarned)
            {
                string master = Instrument.MasterInstrument.Name;
                if (master != "NQ" && master != "MNQ")
                    Draw.TextFixed(this, "MGEVR_SYMWARN",
                        "MGE VOLATILITY REGIME: profile was fitted on NQ. Readings on "
                        + master + " are not validated.",
                        TextPosition.BottomLeft, Brushes.Gold, new SimpleFont("Consolas", 12),
                        Brushes.Transparent, Brushes.Black, 40);
                if (BarsPeriod.BarsPeriodType != BarsPeriodType.Minute || BarsPeriod.Value != 5)
                    Draw.TextFixed(this, "MGEVR_TFWARN",
                        "MGE VOLATILITY REGIME: the profile was fitted on 5-MINUTE bars. "
                        + "This chart is not 5-minute, so the tick readings are not comparable.",
                        TextPosition.BottomRight, Brushes.Gold, new SimpleFont("Consolas", 12),
                        Brushes.Transparent, Brushes.Black, 40);
                symbolWarned = true;
            }

            double tr = Math.Max(High[0] - Low[0],
                        Math.Max(Math.Abs(High[0] - Close[1]), Math.Abs(Low[0] - Close[1])));
            double trTicks = tr / TickSize;

            trueRangeTicks.Add(trTicks);
            int maxKeep = Math.Max(200, LookbackSessions * 78);
            if (trueRangeTicks.Count > maxKeep + 10)
                trueRangeTicks.RemoveRange(0, trueRangeTicks.Count - maxKeep);

            // LEVEL: trailing median of COMPLETED prior bars. Recomputed hourly rather than
            // every bar - a full sort per bar is wasteful and the level moves slowly.
            if (cachedLevelTicks <= 0 || CurrentBar - lastLevelBar >= 12)
            {
                cachedLevelTicks = TrailingMedianExcludingCurrent(maxKeep);
                lastLevelBar = CurrentBar;
            }

            int bucket = EasternBucket();
            bool halt = bucket == HaltBucket || EasternShape[bucket] <= 0;
            double shape = halt ? double.NaN : EasternShape[bucket];
            double expected = (halt || cachedLevelTicks <= 0) ? double.NaN : cachedLevelTicks * shape;

            if (!double.IsNaN(expected))
            {
                ExpectedRange[0] = expected;
                ActualRange[0] = trTicks;
            }
            else
            {
                Values[0].Reset();
                Values[1].Reset();
            }

            UpdateTradePlan(expected);

            if (ShowDashboard)
                DrawDashboard(bucket, halt, shape, expected, trTicks);
        }

        private double TrailingMedianExcludingCurrent(int window)
        {
            int available = trueRangeTicks.Count - 1;      // exclude the bar just closed
            if (available < 20)
                return 0;
            int take = Math.Min(window, available);
            double[] buf = new double[take];
            trueRangeTicks.CopyTo(available - take, buf, 0, take);
            Array.Sort(buf);
            return take % 2 == 1 ? buf[take / 2] : 0.5 * (buf[take / 2 - 1] + buf[take / 2]);
        }

        private int EasternBucket()
        {
            int minutes = Time[0].Hour * 60 + Time[0].Minute + PlatformToEasternOffsetHours * 60;
            minutes = ((minutes % 1440) + 1440) % 1440;
            int bucket = minutes / 30;
            return bucket < 0 ? 0 : (bucket > 47 ? 47 : bucket);
        }

        // ---------------------------------------------------------------------------
        // TRADE PLAN. The direction is the USER'S choice - nothing here suggests a side.
        // What the indicator contributes is the stop DISTANCE, taken from the validated
        // volatility model rather than a fixed tick count, and the bookkeeping that is
        // easy to get wrong by hand: where the targets sit and when to move to breakeven.
        // ---------------------------------------------------------------------------
        private void UpdateTradePlan(double expected)
        {
            if (PlanDirection == MGEPlanDirection.Off || double.IsNaN(expected) || expected <= 0)
            {
                if (planActive)
                    ClearPlanDrawings();
                planActive = false;
                return;
            }

            // Both shows the two brackets for comparison. It is never tracked: you cannot
            // hold a long and a short at once, so "TP1 hit" on one of them would be fiction.
            bool bothSides = PlanDirection == MGEPlanDirection.Both;
            bool wantLong = PlanDirection != MGEPlanDirection.Short;
            int dirCode = bothSides ? 0 : (wantLong ? 1 : -1);
            bool committed = PlanAnchorPrice > 0 && !bothSides;
            double anchor = (PlanAnchorPrice > 0) ? PlanAnchorPrice : Close[0];

            // A plan is FRESH when the intent changed: different side, switched between
            // preview and committed, or a different committed fill price. Compare against
            // the stored values BEFORE overwriting them, or the direction test is dead.
            bool freshPlan = !planActive
                || dirCode != planDirectionUsed
                || committed != planCommitted
                || (committed && Math.Abs(anchor - planAnchorUsed) > TickSize / 2.0);

            // Preview additionally re-prices every bar - that is the point of preview.
            if (freshPlan || !committed)
            {
                planActive = true;
                planIsLong = wantLong;
                planCommitted = committed;
                planDirectionUsed = dirCode;
                planAnchorUsed = anchor;
                planEntry = anchor;
                planRisk = expected * StopRangeMultiple * TickSize;
                planStop = wantLong ? planEntry - planRisk : planEntry + planRisk;
                planTp1 = wantLong ? planEntry + planRisk * Target1R : planEntry - planRisk * Target1R;
                planTp2 = wantLong ? planEntry + planRisk * Target2R : planEntry - planRisk * Target2R;
                planTp3 = wantLong ? planEntry + planRisk * Target3R : planEntry - planRisk * Target3R;

                if (freshPlan)
                {
                    planTp1Hit = planTp2Hit = planTp3Hit = planStopped = false;
                    planStartBar = CurrentBar;
                }

                // Preview re-prices every bar, so keep its lines a fixed short length
                // instead of letting them trail back to wherever preview began.
                if (!committed)
                    planStartBar = CurrentBar;
            }

            // Only a committed plan is tracked. A preview has not been taken, so calling
            // its levels "hit" would be fiction.
            if (planCommitted && !planStopped)
            {
                if (planIsLong)
                {
                    if (!planTp1Hit && High[0] >= planTp1) planTp1Hit = true;
                    if (planTp1Hit && !planTp2Hit && High[0] >= planTp2) planTp2Hit = true;
                    if (planTp2Hit && !planTp3Hit && High[0] >= planTp3) planTp3Hit = true;
                    double live = (planTp1Hit && MoveToBreakevenAtTp1) ? planEntry : planStop;
                    if (Low[0] <= live) planStopped = true;
                }
                else
                {
                    if (!planTp1Hit && Low[0] <= planTp1) planTp1Hit = true;
                    if (planTp1Hit && !planTp2Hit && Low[0] <= planTp2) planTp2Hit = true;
                    if (planTp2Hit && !planTp3Hit && Low[0] <= planTp3) planTp3Hit = true;
                    double live = (planTp1Hit && MoveToBreakevenAtTp1) ? planEntry : planStop;
                    if (High[0] >= live) planStopped = true;
                }
            }

            DrawPlanLevels();
        }

        private double ActiveStopLine()
        {
            return (planCommitted && planTp1Hit && MoveToBreakevenAtTp1) ? planEntry : planStop;
        }

        private void DrawPlanLevels()
        {
            // A zero-length line draws nothing, so give every plan a minimum visible extent.
            // In preview the plan re-arms each bar, which would otherwise be invisible.
            int span = Math.Max(20, CurrentBar - planStartBar);
            int barsAgo = Math.Max(1, Math.Min(CurrentBar, span));
            Brush entryBrush = Brushes.Gold;
            Brush stopBrush = planStopped ? Brushes.Gray
                : (planTp1Hit && MoveToBreakevenAtTp1 ? Brushes.DeepSkyBlue : Brushes.IndianRed);
            Brush tgt = Brushes.LimeGreen;
            Brush dim = Brushes.DimGray;
            double stopLine = ActiveStopLine();

            Draw.Line(this, PlanTag + "_ENTRY", false, barsAgo, planEntry, 0, planEntry,
                entryBrush, DashStyleHelper.Solid, 2);
            Draw.Line(this, PlanTag + "_STOP", false, barsAgo, stopLine, 0, stopLine,
                stopBrush, DashStyleHelper.Dash, 2);
            Draw.Line(this, PlanTag + "_TP1", false, barsAgo, planTp1, 0, planTp1,
                planTp1Hit ? dim : tgt, DashStyleHelper.Dot, 2);
            Draw.Line(this, PlanTag + "_TP2", false, barsAgo, planTp2, 0, planTp2,
                planTp2Hit ? dim : tgt, DashStyleHelper.Dot, 2);
            Draw.Line(this, PlanTag + "_TP3", false, barsAgo, planTp3, 0, planTp3,
                planTp3Hit ? dim : tgt, DashStyleHelper.Solid, 2);

            // Both: mirror the bracket on the other side of the same anchor, for comparison.
            if (PlanDirection == MGEPlanDirection.Both)
            {
                double sStop = planEntry + planRisk;
                double sTp1 = planEntry - planRisk * Target1R;
                double sTp2 = planEntry - planRisk * Target2R;
                double sTp3 = planEntry - planRisk * Target3R;
                Draw.Line(this, PlanTag + "_S_STOP", false, barsAgo, sStop, 0, sStop,
                    Brushes.IndianRed, DashStyleHelper.Dash, 2);
                Draw.Line(this, PlanTag + "_S_TP1", false, barsAgo, sTp1, 0, sTp1, tgt, DashStyleHelper.Dot, 2);
                Draw.Line(this, PlanTag + "_S_TP2", false, barsAgo, sTp2, 0, sTp2, tgt, DashStyleHelper.Dot, 2);
                Draw.Line(this, PlanTag + "_S_TP3", false, barsAgo, sTp3, 0, sTp3, tgt, DashStyleHelper.Solid, 2);
                Draw.Text(this, PlanTag + "_S_STOPTXT", "SHORT STOP", 0, sStop, Brushes.IndianRed);
                Draw.Text(this, PlanTag + "_S_TP1TXT", "S-TP1", 0, sTp1, tgt);
                Draw.Text(this, PlanTag + "_S_TP2TXT", "S-TP2", 0, sTp2, tgt);
                Draw.Text(this, PlanTag + "_S_TP3TXT", "S-TP3 runner", 0, sTp3, tgt);
            }
            else
            {
                ClearShortMirror();
            }

            string mode = PlanDirection == MGEPlanDirection.Both ? " (both, preview)"
                : planCommitted ? "" : " (preview)";
            Draw.Text(this, PlanTag + "_ENTRYTXT", "ENTRY" + mode, 0, planEntry, entryBrush);
            Draw.Text(this, PlanTag + "_STOPTXT",
                planStopped ? "STOPPED" : (planTp1Hit && MoveToBreakevenAtTp1 ? "STOP @ BE" : "STOP"),
                0, stopLine, stopBrush);
            string sidePrefix = PlanDirection == MGEPlanDirection.Both ? "L-" : "";
            Draw.Text(this, PlanTag + "_TP1TXT", planTp1Hit ? "TP1 hit" : sidePrefix + "TP1", 0, planTp1, planTp1Hit ? dim : tgt);
            Draw.Text(this, PlanTag + "_TP2TXT", planTp2Hit ? "TP2 hit" : sidePrefix + "TP2", 0, planTp2, planTp2Hit ? dim : tgt);
            Draw.Text(this, PlanTag + "_TP3TXT", planTp3Hit ? "TP3 hit" : sidePrefix + "TP3 runner", 0, planTp3, planTp3Hit ? dim : tgt);
        }

        private void ClearPlanDrawings()
        {
            foreach (string suffix in new[] { "_ENTRY", "_STOP", "_TP1", "_TP2", "_TP3",
                                              "_ENTRYTXT", "_STOPTXT", "_TP1TXT", "_TP2TXT", "_TP3TXT" })
                RemoveDrawObject(PlanTag + suffix);
            ClearShortMirror();
        }

        private void ClearShortMirror()
        {
            foreach (string suffix in new[] { "_S_STOP", "_S_TP1", "_S_TP2", "_S_TP3",
                                              "_S_STOPTXT", "_S_TP1TXT", "_S_TP2TXT", "_S_TP3TXT" })
                RemoveDrawObject(PlanTag + suffix);
        }

        // Split the affordable size across the three legs. With fewer than 3 contracts a
        // three-leg exit is arithmetically impossible, and the caller is told so plainly.
        private string PlanSizingText(double tickValue)
        {
            double stopTicks = planRisk / TickSize;
            double riskPerContract = stopTicks * tickValue;
            int total = riskPerContract > 0 ? (int)Math.Floor(RiskDollarsPerTrade / riskPerContract) : 0;
            if (total <= 0)
                return "  size: 0 contracts at this risk budget - see above\n";
            if (total == 1)
                return "  size: 1 contract - single exit only, no scaling possible\n";
            if (total == 2)
                return "  size: 2 contracts - 1 at TP1, 1 at TP2 (no runner)\n"
                     + "        this IS the two-leg structure the backtest modelled\n";
            int leg1 = (int)Math.Ceiling(total / 3.0);
            int leg2 = (int)Math.Ceiling((total - leg1) / 2.0);
            int runner = total - leg1 - leg2;
            return string.Format("  size: {0} contracts - {1} at TP1, {2} at TP2, {3} runner to TP3\n",
                total, leg1, leg2, runner);
        }

        private string PlanText(double tickValue)
        {
            if (!planActive)
                return "TRADE PLAN         : Off  (set Plan direction to Long or Short)\n";

            double stopTicks = planRisk / TickSize;
            double riskPerContract = stopTicks * tickValue;

            if (PlanDirection == MGEPlanDirection.Both)
            {
                return string.Format(
                      "TRADE PLAN (BOTH)  comparison only - pick a side to track\n"
                    + "  anchor {0:0.00}   stop distance {1:0}t (${2:0}/contract)\n"
                    + "  LONG   TP1 {3:0.00}  TP2 {4:0.00}  TP3 {5:0.00}   stop {6:0.00}\n"
                    + "  SHORT  TP1 {7:0.00}  TP2 {8:0.00}  TP3 {9:0.00}   stop {10:0.00}\n",
                    planEntry, stopTicks, riskPerContract,
                    planTp1, planTp2, planTp3, planEntry - planRisk,
                    planEntry - planRisk * Target1R, planEntry - planRisk * Target2R,
                    planEntry - planRisk * Target3R, planEntry + planRisk)
                    + PlanSizingText(tickValue)
                    + "  set Plan direction to Long or Short, then enter your fill, to track\n";
            }

            string state = planStopped
                ? (planTp1Hit ? "CLOSED at breakeven" : "STOPPED OUT")
                : planTp3Hit ? "TP3 done - flat"
                : planTp2Hit ? "TP2 hit - runner live to TP3"
                : planTp1Hit ? (MoveToBreakevenAtTp1 ? "TP1 HIT -> MOVE STOP TO BREAKEVEN NOW" : "TP1 hit")
                : planCommitted ? "live - waiting on TP1" : "preview only, not committed";

            return string.Format(
                  "TRADE PLAN ({0})  {1}\n"
                + "  entry {2:0.00}   stop {3:0.00}   ({4:0}t, ${5:0}/contract)\n"
                + "  TP1 {6:0.00} ({7:0.0}R)   TP2 {8:0.00} ({9:0.0}R)   TP3 {10:0.00} ({11:0.0}R)\n",
                planIsLong ? "LONG" : "SHORT", state,
                planEntry, ActiveStopLine(), stopTicks, riskPerContract,
                planTp1, Target1R, planTp2, Target2R, planTp3, Target3R)
                + PlanSizingText(tickValue)
                + (planCommitted ? "" : "  type your fill into 'Plan anchor price' to commit and track it\n");
        }

        // When the budget cannot fund even one contract, say WHY and what would work.
        // A bare "0 contract(s)" reports a result without the reason or the way out.
        private string BudgetShortfallAdvice(double stopTicks, double stopDollars,
                                             double expected, double tickValue)
        {
            double maxStopTicks = tickValue > 0 ? RiskDollarsPerTrade / tickValue : 0;
            double multipleThatFits = expected > 0 ? maxStopTicks / expected : 0;
            string advice = string.Format(
                "    needs ${0:0}, or a stop <= {1:0}t ({2:0.00}x normal)\n",
                stopDollars, maxStopTicks, multipleThatFits);

            // NQ -> MNQ is a 10:1 tick-value step. Name it rather than leaving a bare zero.
            if (Instrument.MasterInstrument.Name == "NQ")
            {
                double microRisk = stopDollars / 10.0;
                int microContracts = microRisk > 0
                    ? (int)Math.Floor(RiskDollarsPerTrade / microRisk) : 0;
                advice += string.Format("    MNQ instead : ${0:0}/contract = {1} contract(s)\n",
                    microRisk, microContracts);
            }
            return advice;
        }

        private static string RegimeState(double ratio)
        {
            if (double.IsNaN(ratio)) return "NO DATA";
            if (ratio < 0.70) return "COMPRESSED";
            if (ratio < 1.30) return "NORMAL";
            if (ratio < 2.00) return "ELEVATED";
            return "EXTREME";
        }

        private void DrawDashboard(int bucket, bool halt, double shape, double expected, double trTicks)
        {
            // The ACTUAL Eastern clock, not the bucket's start. Printing bucket*30 as "ET"
            // read 16:30 on a 16:55 bar - a 25-minute lie on the one field used to sanity
            // check the timezone offset.
            int etMinutes = ((Time[0].Hour * 60 + Time[0].Minute
                              + PlatformToEasternOffsetHours * 60) % 1440 + 1440) % 1440;
            int bucketStart = bucket * 30;
            double ratio = (double.IsNaN(expected) || expected <= 0) ? double.NaN : trTicks / expected;

            double stopTicks = double.IsNaN(expected) ? double.NaN : expected * StopRangeMultiple;
            double tickValue = Instrument.MasterInstrument.PointValue * TickSize;
            double stopDollars = double.IsNaN(stopTicks) ? double.NaN : stopTicks * tickValue;
            int contracts = (double.IsNaN(stopDollars) || stopDollars <= 0)
                ? 0 : (int)Math.Floor(RiskDollarsPerTrade / stopDollars);

            string text =
                "MGE NQ VOLATILITY REGIME   -   INDICATOR ONLY, PLACES NO ORDERS\n"
                + "-------------------------------------------------------------\n"
                + string.Format("Bar close          : {0:HH:mm}   (ET {1:00}:{2:00}, offset {3:+0;-0}h)\n"
                              + "Profile bucket     : ET {4:00}:{5:00}-{6:00}:{7:00}\n",
                    Time[0], etMinutes / 60, etMinutes % 60, PlatformToEasternOffsetHours,
                    bucketStart / 60, bucketStart % 60,
                    ((bucketStart + 30) / 60) % 24, (bucketStart + 30) % 60)
                + (halt
                    ? "Session            : MAINTENANCE HALT - no profile\n"
                    : string.Format("Time-of-day shape  : {0:0.00}x  ({1})\n", shape,
                        shape >= 1.30 ? "a busy part of the day"
                        : shape <= 0.70 ? "a quiet part of the day" : "an ordinary part of the day"))
                + string.Format("Trailing level     : {0:0} ticks   ({1} sessions)\n",
                    cachedLevelTicks, LookbackSessions)
                + "-------------------------------------------------------------\n"
                + (double.IsNaN(expected)
                    ? "NORMAL RANGE NOW   : warming up / halt\n"
                    : string.Format("NORMAL RANGE NOW   : {0:0} ticks per 5-min bar\n", expected))
                + string.Format("This bar's range   : {0:0} ticks\n", trTicks)
                + (double.IsNaN(ratio)
                    ? "REGIME             : NO DATA\n"
                    : string.Format("REGIME             : {0:0.00}x  {1}\n", ratio, RegimeState(ratio)))
                + "-------------------------------------------------------------\n"
                + "SIZING REFERENCE (no directional opinion implied)\n"
                + (double.IsNaN(stopTicks)
                    ? "  unavailable\n"
                    : string.Format("  Stop at {0:0.0}x normal : {1:0} ticks\n"
                                  + "  Risk per contract  : ${2:0}   ({3}, ${4:0.00}/tick)\n"
                                  + "  For a ${5:0} budget   : {6} contract(s){7}\n",
                        StopRangeMultiple, stopTicks, stopDollars,
                        Instrument.MasterInstrument.Name, tickValue,
                        RiskDollarsPerTrade, contracts,
                        contracts > 0 ? "" : "   <-- too small")
                      + (contracts > 0 ? "" : BudgetShortfallAdvice(stopTicks, stopDollars, expected, tickValue)))
                + "-------------------------------------------------------------\n"
                + PlanText(tickValue)
                + "-------------------------------------------------------------\n"
                + "VALIDATION (train 2020-23, tested on untouched 2024-26)\n"
                + "  level only     MAE 43.05t  R2 0.010  medAPE 45.3%\n"
                + "  level x shape  MAE 36.30t  R2 0.042  medAPE 36.1%\n"
                + "  shape stability r=+0.997 / +0.989 / +0.950 (24/25/26)\n"
                + "USE FOR SIZING, NOT FILTERING. The regime ratio was tested as a\n"
                + "trade filter and did NOT predict outcomes (t=-1.87, CI spans 0).";

            Draw.TextFixed(this, "MGEVR_DASH", text, TextPosition.TopRight,
                Brushes.White, new SimpleFont("Consolas", 12),
                Brushes.MidnightBlue, Brushes.MidnightBlue, 85);
        }

        #region Plot accessors
        [Browsable(false)]
        [XmlIgnore]
        public Series<double> ExpectedRange
        {
            get { return Values[0]; }
        }

        [Browsable(false)]
        [XmlIgnore]
        public Series<double> ActualRange
        {
            get { return Values[1]; }
        }
        #endregion
    }
}
