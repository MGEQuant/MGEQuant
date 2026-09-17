#region Using declarations
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Globalization;
using System.Linq;
using System.Text;
using System.Windows.Media;
using System.Xml.Serialization;
using NinjaTrader.Cbi;
using NinjaTrader.Data;
using NinjaTrader.Gui;
using NinjaTrader.Gui.Chart;
using NinjaTrader.Gui.Tools;
using NinjaTrader.NinjaScript;
using NinjaTrader.NinjaScript.DrawingTools;
#endregion

// -----------------------------------------------------------------------------
// Liquidity Heatmap for NinjaTrader 8
//
// Draws a price x time liquidity heatmap plus the levels that liquidity hides
// behind, on any instrument NT8 can chart: futures, stocks, crypto, forex.
//
// Layers (all derived from standard OHLCV bars - no Order Flow+ required):
//   TradedVolume      volume-at-price, how much business each price did
//   RestingLiquidity  volume that wicked past the body and was rejected
//   DeltaPressure     buy vs sell pressure per price bin (bar-direction proxy)
//   LiquidationBands  volume anchors x leverage ladder (estimated clusters)
//
// Levels drawn on top:
//   * swing liquidity pools (equal highs / equal lows) with sweep counts
//   * liquidity sweeps (level taken, then reclaimed) as diamonds
//   * round number handles (auto step from price magnitude)
//   * estimated liquidation bands, HVN magnets, LVN voids and session levels
//
// The analytics mirror MGEQuant/LiquidityHeatmap/liquidity_heatmap.py so a
// backtest and this chart agree on the same numbers.
// -----------------------------------------------------------------------------
namespace NinjaTrader.NinjaScript.Indicators
{
    public class MGE_LiquidityHeatmap : Indicator
    {
        #region Enums

        public enum LiquidityLayer
        {
            TradedVolume,
            RestingLiquidity,
            DeltaPressure,
            LiquidationBands
        }

        /// <summary>Which field the right-side liquidity ladder plots.</summary>
        public enum LadderMetric
        {
            RestingLiquidity,
            TradedVolume,
            DeltaPressure
        }

        private enum PoolKind
        {
            High,
            Low
        }

        private enum LiquiditySide
        {
            BuySide,
            SellSide
        }

        #endregion

        #region Model types

        private class PriceBin
        {
            public double Volume;
            public double Tpo;
            public double Buy;
            public double Sell;
            public double RestingUp;
            public double RestingDown;
        }

        private class LiquidityPool
        {
            public PoolKind Kind;
            public LiquiditySide Side;
            public double Price;
            public int Touches;
            public int Sweeps;
            public int LastSweepBar;
            public int LastIndex;
            public double Strength;
            public double Distance;
        }

        private class LiquidityVoid
        {
            public double Low;
            public double High;
            public double Center;
            public int Bins;
            public double Depth;
            public double Score;
        }

        private class RoundLevel
        {
            public double Price;
            public double Step;
            public bool Major;
            public double Distance;
        }

        private class SweepMark
        {
            public int BarIndex;
            public double Price;
            public LiquiditySide Side;
        }

        private class HeatModel
        {
            public int StartIndex;
            public int Bars;
            public int Bins;
            public double PriceLow;
            public double PriceHigh;
            public double BinSize;
            public double Atr;
            public double Tolerance;
            public double TickSize;

            public PriceBin[] Profile;
            public double[,,] Matrix;             // [layer, bin, column]
            public double[] MatrixMax = new double[4];
            public double MatrixMaxAbs;           // for the diverging delta layer

            public readonly List<LiquidityPool> Pools = new List<LiquidityPool>();
            public readonly List<LiquidityVoid> Voids = new List<LiquidityVoid>();
            public readonly List<RoundLevel> Rounds = new List<RoundLevel>();
            public readonly List<SweepMark> Sweeps = new List<SweepMark>();
            public readonly List<double> NodePrices = new List<double>();
            public readonly List<double> NodeShares = new List<double>();

            public double Price;
            public double PriorHigh, PriorLow, PriorClose;
            public double SessionHigh, SessionLow;
            public double OpeningHigh, OpeningLow;
            public int OpeningBars;
            public double WeekHigh, WeekLow;
            public double Vwap;
            public double RestingAbove, RestingBelow;
            public int SweepsTotal, SweptLevels, PoolCount;
            public double DeltaBias;
            public double LiqAbove, LiqBelow;
            public string Bias;

            public int BinOf(double price)
            {
                if (BinSize <= 0)
                    return 0;
                int idx = (int)((price - PriceLow) / BinSize);
                return idx < 0 ? 0 : (idx >= Bins ? Bins - 1 : idx);
            }

            public double BinCenter(int index)
            {
                return PriceLow + (index + 0.5) * BinSize;
            }

            public double RestingOf(int index)
            {
                return Profile[index].RestingUp + Profile[index].RestingDown;
            }

            public double DeltaOf(int index)
            {
                return Profile[index].Buy - Profile[index].Sell;
            }
        }

        #endregion

        #region Properties

        [Display(Name = "Show heatmap", Description = "Draw the price x time liquidity heat field", Order = 1, GroupName = "Heatmap")]
        public bool ShowHeatmap { get; set; }

        [Display(Name = "Layer", Description = "Which liquidity field the heatmap shows", Order = 2, GroupName = "Heatmap")]
        public LiquidityLayer Layer { get; set; }

        [Display(Name = "Heat opacity", Description = "Heat field opacity in percent (keeps candles readable)", Order = 3, GroupName = "Heatmap")]
        [Range(5, 100)]
        public int HeatOpacity { get; set; }

        [Display(Name = "Lookback bars", Description = "Bars used to build the liquidity picture", Order = 4, GroupName = "Engine")]
        [Range(20, 5000)]
        public int LookbackBars { get; set; }

        [Display(Name = "Price bins", Description = "Price rows in the heat field (12-400)", Order = 5, GroupName = "Engine")]
        [Range(12, 400)]
        public int PriceBins { get; set; }

        [Display(Name = "Pivot strength", Description = "Bars either side of a swing high/low", Order = 6, GroupName = "Engine")]
        [Range(1, 10)]
        public int PivotStrength { get; set; }

        [Display(Name = "Pool tolerance ticks", Description = "How close two swing levels must be to count as equal highs/lows. 0 = auto (10% ATR)", Order = 7, GroupName = "Engine")]
        [Range(0, 200)]
        public double PoolToleranceTicks { get; set; }

        [Display(Name = "Liquidation leverages", Description = "Comma separated leverage ladder for estimated liquidation bands", Order = 8, GroupName = "Engine")]
        public string LiquidationLeverages { get; set; }

        [Display(Name = "Liquidation anchors", Description = "Number of high volume nodes used as liquidation anchors", Order = 9, GroupName = "Engine")]
        [Range(2, 12)]
        public int LiquidationAnchors { get; set; }

        [Display(Name = "Refresh every N bars", Description = "How often the model is rebuilt (1 = every bar close)", Order = 10, GroupName = "Engine")]
        [Range(1, 100)]
        public int RefreshEveryBars { get; set; }

        [Display(Name = "Show pools", Description = "Draw swing liquidity pools (equal highs / equal lows)", Order = 1, GroupName = "Levels")]
        public bool ShowPools { get; set; }

        [Display(Name = "Max pools shown", Description = "How many of the strongest pools to label", Order = 2, GroupName = "Levels")]
        [Range(0, 25)]
        public int MaxPoolsShown { get; set; }

        [Display(Name = "Show sweeps", Description = "Mark liquidity sweeps (level taken then reclaimed)", Order = 3, GroupName = "Levels")]
        public bool ShowSweeps { get; set; }

        [Display(Name = "Max sweep markers", Description = "Most recent sweeps marked on the chart", Order = 4, GroupName = "Levels")]
        [Range(0, 200)]
        public int MaxSweepMarkers { get; set; }

        [Display(Name = "Show round numbers", Description = "Draw round number handles (stop cluster levels)", Order = 5, GroupName = "Levels")]
        public bool ShowRoundNumbers { get; set; }

        [Display(Name = "Show session levels", Description = "Draw prior day, opening range, week high/low and VWAP", Order = 6, GroupName = "Levels")]
        public bool ShowSessionLevels { get; set; }

        [Display(Name = "Show level tags", Description = "Name every key level on the chart (POC, HVN, LVN, PDH, PDL, VWAP, ORH/ORL, WH/WL) with a label pinned to the last candle", Order = 8, GroupName = "Levels")]
        public bool ShowLevelTags { get; set; }

        [Display(Name = "Show live arrows", Description = "Arrow on the last candle for each live level - redrawn every bar so it slides with new prints", Order = 9, GroupName = "Levels")]
        public bool ShowLiveArrows { get; set; }

        [Display(Name = "Show voids", Description = "Mark the largest liquidity void (low volume travel zone)", Order = 10, GroupName = "Levels")]
        public bool ShowVoids { get; set; }

        [Display(Name = "Show summary", Description = "Draw the liquidity summary panel on the chart", Order = 1, GroupName = "Display")]
        public bool ShowSummary { get; set; }

        [Display(Name = "Text size", Description = "Font size for chart labels", Order = 2, GroupName = "Display")]
        [Range(8, 16)]
        public int TextFontSize { get; set; }

        [Display(Name = "Show liquidity ladder", Description = "Draw a volume-profile style liquidity histogram in the right margin", Order = 3, GroupName = "Display")]
        public bool ShowLadder { get; set; }

        [Display(Name = "Ladder metric", Description = "Which field the ladder plots: resting liquidity, traded volume or delta pressure", Order = 4, GroupName = "Display")]
        public LadderMetric LadderMetricChoice { get; set; }

        [Display(Name = "Ladder width", Description = "Histogram strip width in percent of the panel width (5-45)", Order = 5, GroupName = "Display")]
        [Range(5, 45)]
        public int LadderWidthPercent { get; set; }

        [Display(Name = "Ladder opacity", Description = "Ladder bar opacity in percent (20-100)", Order = 6, GroupName = "Display")]
        [Range(20, 100)]
        public int LadderOpacity { get; set; }

        #endregion

        #region Fields

        private HeatModel model;

        private SharpDX.Direct2D1.Brush heatCellBrush;     // per frame, disposed after draw
        private byte heatCellR;
        private byte heatCellG;
        private byte heatCellB;

        private int lastBuildBar = -1;
        private int previousPoolLabels;
        private int previousSweepMarks;
        private int previousRoundLabels;
        private int previousLevelRows;
        private double[] leverages = new double[] { 10, 20, 50, 100 };

        private System.Windows.Media.Brush brushPoolAbove;
        private System.Windows.Media.Brush brushPoolBelow;
        private System.Windows.Media.Brush brushSweepBuy;
        private System.Windows.Media.Brush brushSweepSell;
        private System.Windows.Media.Brush brushRound;
        private System.Windows.Media.Brush brushVoid;
        private System.Windows.Media.Brush brushLevel;
        private System.Windows.Media.Brush brushText;
        private SimpleFont labelFont;
        private bool resourcesReady;

        private SharpDX.Direct2D1.Brush ladderBrush;             // per frame, disposed after draw
        private SharpDX.Direct2D1.Brush ladderBuyBrush;
        private SharpDX.Direct2D1.Brush ladderSellBrush;
        private SharpDX.Direct2D1.Brush ladderPocBrush;
        private SharpDX.Direct2D1.Brush ladderZeroBrush;
        private SharpDX.Direct2D1.Brush ladderTintBrush;

        private const string SummaryTag = "LH_Summary";
        private const string PoolTagPrefix = "LH_Pool_";
        private const string PoolTextTagPrefix = "LH_PoolTxt_";
        private const string RoundTagPrefix = "LH_Round_";
        private const string SweepTagPrefix = "LH_Sweep_";
        private const string VoidTag = "LH_Void";
        private const string LevelNamePrefix = "LH_Lvl_";
        private const string LiveArrowPrefix = "LH_Move_";

        private static readonly CultureInfo Inv = CultureInfo.InvariantCulture;

        #endregion

        #region Lifecycle

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Name = "Liquidity Heatmap";
                Description = "Price x time liquidity heatmap with swing liquidity pools, sweeps, "
                            + "round number handles, HVN/LVN voids and estimated liquidation bands. "
                            + "Works on futures, stocks, crypto and forex using standard OHLCV bars.";
                IsOverlay = true;
                Calculate = Calculate.OnBarClose;
                DisplayInDataBox = false;
                DrawOnPricePanel = true;
                PaintPriceMarkers = false;
                BarsRequiredToPlot = 1;

                ShowHeatmap = true;
                Layer = LiquidityLayer.RestingLiquidity;
                HeatOpacity = 45;
                LookbackBars = 300;
                PriceBins = 80;
                PivotStrength = 3;
                PoolToleranceTicks = 0;
                LiquidationLeverages = "10,20,50,100";
                LiquidationAnchors = 6;
                RefreshEveryBars = 1;
                ShowPools = true;
                MaxPoolsShown = 6;
                ShowSweeps = true;
                MaxSweepMarkers = 25;
                ShowRoundNumbers = false;
                ShowSessionLevels = true;
                ShowLevelTags = true;
                ShowLiveArrows = true;
                ShowVoids = false;
                ShowSummary = true;
                TextFontSize = 11;

                ShowLadder = true;
                LadderMetricChoice = LadderMetric.RestingLiquidity;
                LadderWidthPercent = 18;
                LadderOpacity = 70;
            }
            else if (State == State.DataLoaded)
            {
                EnsureResources();
                leverages = ParseLeverages(LiquidationLeverages);
            }
            else if (State == State.Terminated)
            {
                if (heatCellBrush != null)
                {
                    heatCellBrush.Dispose();
                    heatCellBrush = null;
                }
                DisposeLadderBrushes();
            }
        }

        protected override void OnBarUpdate()
        {
            if (BarsInProgress != 0)
                return;
            if (CurrentBar < 10)
                return;

            bool rebuild = model == null
                        || CurrentBar - lastBuildBar >= Math.Max(1, RefreshEveryBars)
                        || CurrentBar < lastBuildBar;

            if (!rebuild)
            {
                if (model != null)
                    DrawLevelNamesAndArrows(model);
                ForceRefresh();
                return;
            }

            leverages = ParseLeverages(LiquidationLeverages);
            model = BuildModel();
            lastBuildBar = CurrentBar;

            if (model != null)
                DrawLevelsAndSummary(model);

            ForceRefresh();
        }

        protected override void OnRender(ChartControl chartControl, ChartScale chartScale)
        {
            if (model == null || RenderTarget == null || ChartPanel == null || ChartBars == null)
                return;

            if (ShowHeatmap)
                DrawHeatField(chartControl, chartScale);

            if (ShowLadder)
                DrawLadder(chartScale);
        }

        #endregion

        #region Liquidity ladder

        /// <summary>
        /// D2D brushes are cheap, so the ladder rebuilds them every frame -
        /// NT8 can recreate the render target on resize, and brushes bound to
        /// a dead target throw.
        /// </summary>
        private void EnsureLadderBrushes()
        {
            DisposeLadderBrushes();

            float alpha = Math.Min(1f, Math.Max(0.2f, LadderOpacity / 100f));
            ladderTintBrush = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget,
                new SharpDX.Color4(0f, 0f, 0f, 0.45f));
            ladderBrush = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget,
                new SharpDX.Color4(226f / 255f, 168f / 255f, 92f / 255f, alpha));
            ladderBuyBrush = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget,
                new SharpDX.Color4(96f / 255f, 190f / 255f, 122f / 255f, alpha));
            ladderSellBrush = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget,
                new SharpDX.Color4(232f / 255f, 92f / 255f, 122f / 255f, alpha));
            ladderPocBrush = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget,
                new SharpDX.Color4(1f, 214f / 255f, 102f / 255f, 0.95f));
            ladderZeroBrush = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget,
                new SharpDX.Color4(0.55f, 0.55f, 0.55f, 0.75f));
        }

        private void DisposeLadderBrushes()
        {
            if (ladderBrush != null) { ladderBrush.Dispose(); ladderBrush = null; }
            if (ladderBuyBrush != null) { ladderBuyBrush.Dispose(); ladderBuyBrush = null; }
            if (ladderSellBrush != null) { ladderSellBrush.Dispose(); ladderSellBrush = null; }
            if (ladderPocBrush != null) { ladderPocBrush.Dispose(); ladderPocBrush = null; }
            if (ladderZeroBrush != null) { ladderZeroBrush.Dispose(); ladderZeroBrush = null; }
            if (ladderTintBrush != null) { ladderTintBrush.Dispose(); ladderTintBrush = null; }
        }

        /// <summary>
        /// Volume-profile style liquidity histogram drawn in the chart's right
        /// margin. Resting liquidity and traded volume bars grow from the left
        /// edge of the strip; the delta metric diverges from a centre line
        /// (buy side right, sell side left). The strongest bin of the chosen
        /// metric is highlighted and labelled as the POC.
        /// </summary>
        private void DrawLadder(ChartScale chartScale)
        {
            int bins = model.Bins;
            if (bins < 2 || ChartPanel.W < 60)
                return;

            EnsureLadderBrushes();
            try
            {
                float panelRight = ChartPanel.X + ChartPanel.W;
                float panelBottom = ChartPanel.Y + ChartPanel.H;
                float ladderWidth = ChartPanel.W * Math.Min(0.45f, Math.Max(0.05f, LadderWidthPercent / 100f));
                float ladderLeft = panelRight - ladderWidth;

                // reserve the strip: dim whatever is under it so the ladder
                // never fights the heat field for attention
                RenderTarget.FillRectangle(new SharpDX.RectangleF(
                    ladderLeft, ChartPanel.Y, ladderWidth, ChartPanel.H), ladderTintBrush);
                RenderTarget.DrawLine(new SharpDX.Vector2(ladderLeft, ChartPanel.Y),
                    new SharpDX.Vector2(ladderLeft, panelBottom), ladderZeroBrush, 1f);

                bool diverging = LadderMetricChoice == LadderMetric.DeltaPressure;
                float axisX = diverging ? ladderLeft + ladderWidth * 0.5f : ladderLeft;
                float maxExtent = diverging ? ladderWidth * 0.46f : ladderWidth * 0.94f;

                double[] values = new double[bins];
                double max = 0;
                for (int b = 0; b < bins; b++)
                {
                    double value;
                    if (LadderMetricChoice == LadderMetric.TradedVolume)
                        value = model.Profile[b].Volume;
                    else if (LadderMetricChoice == LadderMetric.DeltaPressure)
                        value = model.DeltaOf(b);
                    else
                        value = model.RestingOf(b);
                    values[b] = value;
                    double magnitude = Math.Abs(value);
                    if (magnitude > max)
                        max = magnitude;
                }
                if (max <= 0)
                    return;

                int pocBin = 0;
                for (int b = 1; b < bins; b++)
                    if (Math.Abs(values[b]) > Math.Abs(values[pocBin]))
                        pocBin = b;

                for (int b = 0; b < bins; b++)
                {
                    float binTop = chartScale.GetYByValue(model.PriceLow + (b + 1) * model.BinSize);
                    float binBottom = chartScale.GetYByValue(model.PriceLow + b * model.BinSize);
                    if (binBottom < ChartPanel.Y || binTop > panelBottom)
                        continue;                   // row is scrolled out of view
                    float height = Math.Max(1f, binBottom - binTop);

                    double magnitude = Math.Abs(values[b]) / max;
                    if (magnitude < 0.02)
                        continue;
                    float barLength = (float)(maxExtent * magnitude);

                    SharpDX.Direct2D1.Brush brush;
                    SharpDX.RectangleF barRect;
                    if (diverging)
                    {
                        brush = values[b] >= 0 ? ladderBuyBrush : ladderSellBrush;
                        barRect = values[b] >= 0
                            ? new SharpDX.RectangleF(axisX, binTop, barLength, height)
                            : new SharpDX.RectangleF(axisX - barLength, binTop, barLength, height);
                    }
                    else
                    {
                        brush = ladderBrush;
                        barRect = new SharpDX.RectangleF(axisX, binTop, barLength, height);
                    }
                    RenderTarget.FillRectangle(barRect, brush);
                }

                if (diverging)
                    RenderTarget.DrawLine(new SharpDX.Vector2(axisX, ChartPanel.Y),
                        new SharpDX.Vector2(axisX, panelBottom), ladderZeroBrush, 1f);

                DrawLadderPoc(chartScale, pocBin, ladderLeft, ladderWidth, panelRight, panelBottom);
            }
            catch (Exception)
            {
                // a lost render target mid-frame is fatal for this frame only
            }
            finally
            {
                DisposeLadderBrushes();
            }
        }

        private void DrawLadderPoc(ChartScale chartScale, int pocBin, float ladderLeft,
            float ladderWidth, float panelRight, float panelBottom)
        {
            float pocTop = chartScale.GetYByValue(model.PriceLow + (pocBin + 1) * model.BinSize);
            float pocBottom = chartScale.GetYByValue(model.PriceLow + pocBin * model.BinSize);
            float pocY = (pocTop + pocBottom) / 2f;
            if (pocY < ChartPanel.Y || pocY > panelBottom)
                return;

            // POC line only: DirectWrite text was removed so the indicator
            // compiles with the default NinjaScript reference set.
            RenderTarget.DrawLine(new SharpDX.Vector2(ladderLeft, pocY),
                new SharpDX.Vector2(panelRight, pocY), ladderPocBrush, 2f);
        }


        #endregion

        #region Model building

        private HeatModel BuildModel()
        {
            int total = CurrentBar + 1;
            if (total < 12)
                return null;

            int count = Math.Min(Math.Max(20, LookbackBars), total);
            int start = total - count;
            int bins = Math.Max(12, Math.Min(400, PriceBins));

            double low = double.MaxValue;
            double high = double.MinValue;
            for (int i = start; i < total; i++)
            {
                double h = HighAt(i);
                double l = LowAt(i);
                if (h > high) high = h;
                if (l < low) low = l;
            }
            if (!(high > low))
                high = low + Math.Max(TickSize, 0.0000001) * 10.0;

            HeatModel m = new HeatModel();
            m.StartIndex = start;
            m.Bars = count;
            m.Bins = bins;
            m.PriceLow = low;
            m.PriceHigh = high;
            m.BinSize = (high - low) / bins;
            m.TickSize = TickSize > 0 ? TickSize : 0.01;
            m.Price = CloseAt(total - 1);
            m.Atr = ComputeAtr(start, total);
            m.Tolerance = PoolToleranceTicks > 0
                ? PoolToleranceTicks * m.TickSize
                : Math.Max(m.TickSize, 0.10 * m.Atr);

            BuildProfileAndMatrix(m);
            FindNodes(m);
            FindVoids(m);
            BuildPools(m);
            BuildRoundLevels(m);
            BuildSessionLevels(m);
            Summarise(m);
            return m;
        }

        private double ComputeAtr(int start, int total)
        {
            const int period = 14;
            int from = Math.Max(start + 1, total - period);
            double sum = 0;
            int n = 0;
            for (int i = from; i < total; i++)
            {
                double previousClose = CloseAt(i - 1);
                double tr = Math.Max(HighAt(i) - LowAt(i),
                            Math.Max(Math.Abs(HighAt(i) - previousClose),
                                     Math.Abs(LowAt(i) - previousClose)));
                sum += tr;
                n++;
            }
            if (n == 0)
                return 0;
            return sum / n;
        }

        private void BuildProfileAndMatrix(HeatModel m)
        {
            m.Profile = new PriceBin[m.Bins];
            for (int b = 0; b < m.Bins; b++)
                m.Profile[b] = new PriceBin();
            m.Matrix = new double[4, m.Bins, m.Bars];

            const int tradedLayer = (int)LiquidityLayer.TradedVolume;
            const int restingLayer = (int)LiquidityLayer.RestingLiquidity;
            const int deltaLayer = (int)LiquidityLayer.DeltaPressure;

            for (int column = 0; column < m.Bars; column++)
            {
                int i = m.StartIndex + column;
                double o = OpenAt(i);
                double h = HighAt(i);
                double l = LowAt(i);
                double c = CloseAt(i);
                double v = VolumeAt(i);

                double range = Math.Max(h - l, m.BinSize);
                int first = m.BinOf(l);
                int last = m.BinOf(h);
                int span = last - first + 1;
                double share = v / span;
                bool buySide = c >= o;

                for (int b = first; b <= last; b++)
                {
                    PriceBin bin = m.Profile[b];
                    bin.Volume += share;
                    bin.Tpo += 1.0;
                    if (buySide)
                        bin.Buy += share;
                    else
                        bin.Sell += share;

                    AddHeat(m, tradedLayer, b, column, share);
                    AddHeat(m, deltaLayer, b, column, buySide ? share : -share);
                }

                double bodyHigh = Math.Max(o, c);
                double bodyLow = Math.Min(o, c);
                if (h > bodyHigh)
                {
                    double amount = v * ((h - bodyHigh) / range);
                    int from = m.BinOf(bodyHigh);
                    double piece = amount / (last - from + 1);
                    for (int b = from; b <= last; b++)
                    {
                        m.Profile[b].RestingUp += piece;
                        AddHeat(m, restingLayer, b, column, piece);
                    }
                }
                if (l < bodyLow)
                {
                    double amount = v * ((bodyLow - l) / range);
                    int to = m.BinOf(bodyLow);
                    double piece = amount / (to - first + 1);
                    for (int b = first; b <= to; b++)
                    {
                        m.Profile[b].RestingDown += piece;
                        AddHeat(m, restingLayer, b, column, piece);
                    }
                }
            }

            BuildLiquidationLayer(m);
        }

        private void AddHeat(HeatModel m, int layer, int bin, int column, double value)
        {
            m.Matrix[layer, bin, column] += value;
            double abs = Math.Abs(m.Matrix[layer, bin, column]);
            if (abs > m.MatrixMax[layer])
                m.MatrixMax[layer] = abs;
            if (abs > m.MatrixMaxAbs)
                m.MatrixMaxAbs = abs;
        }

        /// <summary>
        /// Estimated liquidation clusters: high volume anchors projected onto a
        /// leverage ladder, weighted by how recently price interacted with the
        /// anchor, plus the fresh swing extremes for momentum cascades.
        /// </summary>
        private void BuildLiquidationLayer(HeatModel m)
        {
            if (leverages.Length == 0)
                return;

            const int layer = (int)LiquidityLayer.LiquidationBands;
            int anchorCount = Math.Max(2, LiquidationAnchors);
            List<int> picks = new List<int>();
            foreach (int bin in Enumerable.Range(0, m.Bins).OrderByDescending(b => m.Profile[b].Volume))
            {
                if (m.Profile[bin].Volume <= 0)
                    break;
                if (picks.All(p => Math.Abs(p - bin) > 2))
                    picks.Add(bin);
                if (picks.Count >= anchorCount)
                    break;
            }
            if (picks.Count == 0)
                return;

            double maxAnchorVolume = picks.Max(b => m.Profile[b].Volume);
            if (maxAnchorVolume <= 0)
                maxAnchorVolume = 1;
            double sampleVolume = Math.Max(1e-9, m.Profile.Sum(b => b.Volume) / m.Bins);
            double maxLeverage = leverages.Max();
            int freshnessWindow = Math.Max(5, Math.Min(60, Math.Max(5, m.Bars / 5)));

            for (int column = 0; column < m.Bars; column++)
            {
                int i = m.StartIndex + column;

                foreach (int anchorBin in picks)
                {
                    double anchorPrice = m.BinCenter(anchorBin);
                    int touched = 0;
                    for (int j = Math.Max(m.StartIndex, i - freshnessWindow + 1); j <= i; j++)
                    {
                        if (LowAt(j) <= anchorPrice && anchorPrice <= HighAt(j))
                            touched++;
                    }
                    if (touched == 0)
                        continue;

                    double freshness = Math.Min(1.0, touched / (freshnessWindow * 0.25));
                    double baseWeight = (m.Profile[anchorBin].Volume / maxAnchorVolume) * freshness;
                    foreach (double lev in leverages)
                    {
                        double weight = baseWeight * (lev / maxLeverage);
                        AddLiquidation(m, layer, anchorPrice * (1.0 - 1.0 / lev), column, weight);
                        AddLiquidation(m, layer, anchorPrice * (1.0 + 1.0 / lev), column, weight);
                    }
                }

                int windowStart = Math.Max(m.StartIndex, i - freshnessWindow + 1);
                if (windowStart < i)
                {
                    double swingHigh = double.MinValue;
                    double swingLow = double.MaxValue;
                    double volumeSum = 0;
                    for (int j = windowStart; j <= i; j++)
                    {
                        swingHigh = Math.Max(swingHigh, HighAt(j));
                        swingLow = Math.Min(swingLow, LowAt(j));
                        volumeSum += VolumeAt(j);
                    }
                    double momentumVolume = volumeSum / (i - windowStart + 1);
                    double baseWeight = 0.5 * momentumVolume / sampleVolume;
                    foreach (double lev in leverages)
                    {
                        double weight = baseWeight * (lev / maxLeverage);
                        AddLiquidation(m, layer, swingLow * (1.0 - 1.0 / lev), column, weight);
                        AddLiquidation(m, layer, swingHigh * (1.0 + 1.0 / lev), column, weight);
                    }
                }
            }
        }

        private void AddLiquidation(HeatModel m, int layer, double price, int column, double weight)
        {
            if (price < m.PriceLow || price > m.PriceHigh || weight <= 0)
                return;
            AddHeat(m, layer, m.BinOf(price), column, weight);
        }

        private void FindNodes(HeatModel m)
        {
            foreach (int bin in Enumerable.Range(0, m.Bins).OrderByDescending(b => m.Profile[b].Volume))
            {
                if (m.Profile[bin].Volume <= 0)
                    break;
                if (m.NodePrices.All(p => Math.Abs(m.BinOf(p) - bin) > 2))
                {
                    m.NodePrices.Add(m.BinCenter(bin));
                    m.NodeShares.Add(m.Profile[bin].Volume);
                }
                if (m.NodePrices.Count >= 6)
                    break;
            }
            double total = m.Profile.Sum(b => b.Volume);
            if (total <= 0)
                total = 1;
            for (int n = 0; n < m.NodeShares.Count; n++)
                m.NodeShares[n] = m.NodeShares[n] / total * 100.0;
        }

        private void FindVoids(HeatModel m)
        {
            double mean = m.Profile.Where(b => b.Volume > 0).Select(b => b.Volume).DefaultIfEmpty(0).Average();
            if (mean <= 0)
                return;

            double cut = mean * 0.20;
            List<int> run = new List<int>();
            List<List<int>> runs = new List<List<int>>();
            for (int b = 0; b < m.Bins; b++)
            {
                if (m.Profile[b].Volume < cut)
                {
                    run.Add(b);
                }
                else
                {
                    runs.Add(run);
                    run = new List<int>();
                }
            }
            runs.Add(run);

            // fold one-bar gaps together so a void reads as a single zone
            List<List<int>> merged = new List<List<int>>();
            foreach (List<int> candidate in runs)
            {
                if (candidate.Count == 0)
                    continue;
                if (merged.Count > 0)
                {
                    List<int> last = merged[merged.Count - 1];
                    if (candidate[0] - last[last.Count - 1] - 1 <= 1)
                    {
                        last.AddRange(candidate);
                        continue;
                    }
                }
                merged.Add(new List<int>(candidate));
            }

            foreach (List<int> zone in merged)
            {
                double volume = 0;
                foreach (int b in zone)
                    volume += m.Profile[b].Volume;
                double depth = volume / Math.Max(1e-12, mean * zone.Count);
                LiquidityVoid v = new LiquidityVoid();
                v.Low = m.PriceLow + zone[0] * m.BinSize;
                v.High = m.PriceLow + (zone[zone.Count - 1] + 1) * m.BinSize;
                v.Center = (v.Low + v.High) / 2.0;
                v.Bins = zone.Count;
                v.Depth = depth;
                v.Score = zone.Count * (1.0 - Math.Min(1.0, depth));
                m.Voids.Add(v);
            }
            m.Voids.Sort((a, b) => b.Score.CompareTo(a.Score));
        }

        private void BuildPools(HeatModel m)
        {
            int k = Math.Max(1, PivotStrength);
            List<KeyValuePair<int, double>> pivotHighs = new List<KeyValuePair<int, double>>();
            List<KeyValuePair<int, double>> pivotLows = new List<KeyValuePair<int, double>>();
            int from = Math.Max(m.StartIndex + k, k);
            int to = m.StartIndex + m.Bars - k;

            for (int i = from; i < to; i++)
            {
                double hi = HighAt(i);
                double lo = LowAt(i);
                bool isHigh = true;
                bool isLow = true;
                for (int j = i - k; j <= i + k; j++)
                {
                    if (HighAt(j) > hi) isHigh = false;
                    if (LowAt(j) < lo) isLow = false;
                }
                if (isHigh)
                    pivotHighs.Add(new KeyValuePair<int, double>(i, hi));
                if (isLow)
                    pivotLows.Add(new KeyValuePair<int, double>(i, lo));
            }

            AddClusteredPools(m, pivotHighs, PoolKind.High);
            AddClusteredPools(m, pivotLows, PoolKind.Low);
            m.Pools.Sort((a, b) => b.Strength.CompareTo(a.Strength));

            int sweepFrom = m.StartIndex + Math.Max(1, (int)(m.Bars * 0.34));
            foreach (LiquidityPool pool in m.Pools)
            {
                int sweeps = 0;
                int lastSweepBar = -1;
                LiquiditySide lastSide = pool.Side;
                for (int i = Math.Max(sweepFrom, m.StartIndex + 1); i < m.StartIndex + m.Bars; i++)
                {
                    double previousClose = CloseAt(i - 1);
                    if (LowAt(i) < pool.Price - m.Tolerance * 0.5
                        && previousClose >= pool.Price
                        && CloseAt(i) > pool.Price)
                    {
                        sweeps++;
                        lastSweepBar = i;
                        lastSide = LiquiditySide.SellSide;
                    }
                    else if (HighAt(i) > pool.Price + m.Tolerance * 0.5
                        && previousClose <= pool.Price
                        && CloseAt(i) < pool.Price)
                    {
                        sweeps++;
                        lastSweepBar = i;
                        lastSide = LiquiditySide.BuySide;
                    }
                }
                pool.Sweeps = sweeps;
                pool.LastSweepBar = lastSweepBar;
                if (sweeps > 0)
                {
                    SweepMark mark = new SweepMark();
                    mark.BarIndex = lastSweepBar;
                    mark.Price = pool.Price;
                    mark.Side = lastSide;
                    m.Sweeps.Add(mark);
                }
            }
            m.Sweeps.Sort((a, b) => a.BarIndex.CompareTo(b.BarIndex));
        }

        private void AddClusteredPools(HeatModel m, List<KeyValuePair<int, double>> pivots, PoolKind kind)
        {
            if (pivots.Count == 0)
                return;

            List<KeyValuePair<int, double>> ordered = pivots.OrderBy(p => p.Value).ToList();
            List<List<KeyValuePair<int, double>>> clusters = new List<List<KeyValuePair<int, double>>>();
            foreach (KeyValuePair<int, double> pivot in ordered)
            {
                if (clusters.Count > 0)
                {
                    List<KeyValuePair<int, double>> current = clusters[clusters.Count - 1];
                    if (pivot.Value - current[current.Count - 1].Value <= m.Tolerance)
                    {
                        current.Add(pivot);
                        continue;
                    }
                }
                clusters.Add(new List<KeyValuePair<int, double>> { pivot });
            }

            foreach (List<KeyValuePair<int, double>> cluster in clusters)
            {
                LiquidityPool pool = new LiquidityPool();
                pool.Kind = kind;
                pool.Price = cluster.Average(p => p.Value);
                pool.Touches = cluster.Count;
                pool.LastIndex = cluster.Max(p => p.Key);
                pool.Side = pool.Price > m.Price ? LiquiditySide.BuySide : LiquiditySide.SellSide;
                double recency = (double)pool.LastIndex / Math.Max(1, m.Bars);
                pool.Strength = pool.Touches * (0.5 + 0.5 * recency);
                pool.Distance = pool.Price - m.Price;
                m.Pools.Add(pool);
            }
        }

        private void BuildRoundLevels(HeatModel m)
        {
            double magnitude = Math.Pow(10, Math.Floor(Math.Log10(Math.Max(m.Price, 1e-9))));
            double major = magnitude / 100.0;
            double minor = magnitude / 200.0;
            if (major <= 0 || minor <= 0)
                return;

            AddRoundStep(m, minor, false, major);
            AddRoundStep(m, major, true, major);
            m.Rounds.Sort((a, b) => Math.Abs(a.Distance).CompareTo(Math.Abs(b.Distance)));
        }

        private void AddRoundStep(HeatModel m, double step, bool isMajor, double major)
        {
            double start = Math.Floor(m.PriceLow / step) * step;
            double end = Math.Ceiling(m.PriceHigh / step) * step;
            for (double value = start; value <= end + step * 0.5; value += step)
            {
                if (value < m.PriceLow || value > m.PriceHigh)
                    continue;
                // a level that is both a minor and a major handle is reported once
                if (!isMajor && Math.Abs(value / major - Math.Round(value / major)) < 1e-9)
                    continue;
                RoundLevel level = new RoundLevel();
                level.Price = value;
                level.Step = step;
                level.Major = isMajor;
                level.Distance = value - m.Price;
                m.Rounds.Add(level);
            }
        }

        /// <summary>
        /// Prior day, opening range, week high/low and session VWAP.
        /// "Day" means the calendar day of the bar timestamp in chart time.
        /// </summary>
        private void BuildSessionLevels(HeatModel m)
        {
            List<List<int>> sessions = new List<List<int>>();
            List<int> bucket = new List<int>();
            DateTime currentDay = TimeAt(m.StartIndex).Date;

            for (int i = m.StartIndex; i < m.StartIndex + m.Bars; i++)
            {
                DateTime day = TimeAt(i).Date;
                if (day != currentDay && bucket.Count > 0)
                {
                    sessions.Add(bucket);
                    bucket = new List<int>();
                    currentDay = day;
                }
                bucket.Add(i);
            }
            if (bucket.Count > 0)
                sessions.Add(bucket);
            if (sessions.Count == 0)
                return;

            List<int> latest = sessions[sessions.Count - 1];
            m.SessionHigh = latest.Max(i => HighAt(i));
            m.SessionLow = latest.Min(i => LowAt(i));

            int openingBars = Math.Max(1, Math.Min(latest.Count, 8));
            List<int> opening = latest.GetRange(0, openingBars);
            m.OpeningBars = openingBars;
            m.OpeningHigh = opening.Max(i => HighAt(i));
            m.OpeningLow = opening.Min(i => LowAt(i));

            if (sessions.Count >= 2)
            {
                List<int> prior = sessions[sessions.Count - 2];
                m.PriorHigh = prior.Max(i => HighAt(i));
                m.PriorLow = prior.Min(i => LowAt(i));
                m.PriorClose = CloseAt(prior[prior.Count - 1]);
            }

            List<int> week = new List<int>();
            for (int s = Math.Max(0, sessions.Count - 5); s < sessions.Count; s++)
                week.AddRange(sessions[s]);
            if (week.Count > 0)
            {
                m.WeekHigh = week.Max(i => HighAt(i));
                m.WeekLow = week.Min(i => LowAt(i));
            }

            double typical = 0;
            double totalVolume = 0;
            foreach (int i in latest)
            {
                double v = VolumeAt(i);
                typical += ((HighAt(i) + LowAt(i) + CloseAt(i)) / 3.0) * v;
                totalVolume += v;
            }
            m.Vwap = totalVolume > 0 ? typical / totalVolume : CloseAt(latest[latest.Count - 1]);
        }

        private void Summarise(HeatModel m)
        {
            double above = 0;
            double below = 0;
            for (int b = 0; b < m.Bins; b++)
            {
                if (m.BinCenter(b) > m.Price)
                    above += m.RestingOf(b);
                else
                    below += m.RestingOf(b);
            }
            m.RestingAbove = above;
            m.RestingBelow = below;

            if (above > below * 1.15)
                m.Bias = "buy-side liquidity above";
            else if (below > above * 1.15)
                m.Bias = "sell-side liquidity below";
            else
                m.Bias = "balanced";

            double buy = m.Profile.Sum(b => b.Buy);
            double sell = m.Profile.Sum(b => b.Sell);
            double total = buy + sell;
            m.DeltaBias = total > 0 ? (buy - sell) / total : 0;

            m.PoolCount = m.Pools.Count;
            m.SweepsTotal = m.Pools.Sum(p => p.Sweeps);
            m.SweptLevels = m.Pools.Count(p => p.Sweeps > 0);

            const int liqLayer = (int)LiquidityLayer.LiquidationBands;
            double bestAbove = 0;
            double bestBelow = 0;
            for (int b = 0; b < m.Bins; b++)
            {
                double value = m.Matrix[liqLayer, b, m.Bars - 1];
                if (value <= 0)
                    continue;
                if (m.BinCenter(b) > m.Price)
                {
                    if (value > bestAbove) { bestAbove = value; m.LiqAbove = m.BinCenter(b); }
                }
                else if (value > bestBelow) { bestBelow = value; m.LiqBelow = m.BinCenter(b); }
            }
        }

        #endregion

        #region Rendering

        private void DrawHeatField(ChartControl chartControl, ChartScale chartScale)
        {
            int columns = model.Bars;
            if (columns < 2 || model.Bins < 2)
                return;

            // NOTE: intentionally no SharpDX.Direct2D1.Bitmap / DrawBitmap here.
            // The Bitmap type drags in SharpDX.DXGI.Surface overloads, which the
            // default NinjaScript reference set does not include (CS0012).
            // Per-cell FillRectangle brushes use only SharpDX + SharpDX.Direct2D1.
            int firstBar = Math.Max(ChartBars.FromIndex, model.StartIndex);
            int lastBar = Math.Min(ChartBars.ToIndex - 1, model.StartIndex + model.Bars - 1);
            if (lastBar <= firstBar)
                return;

            RenderTarget.AntialiasMode = SharpDX.Direct2D1.AntialiasMode.Aliased;

            int layer = (int)Layer;
            double max = model.MatrixMax[layer];
            if (max <= 0)
                max = 1;

            float opacity = Math.Min(1f, Math.Max(0.05f, HeatOpacity / 100f));

            // Sample stride keeps large lookbacks cheap: draw at most ~8000 cells.
            // Each drawn cell stays exactly one bar wide - the stride skips bars
            // instead of merging them, so a thinned-out frame looks like a sparser
            // heat field (small gaps) rather than blocky merged rectangles.
            int totalCells = (lastBar - firstBar + 1) * model.Bins;
            int stride = Math.Max(1, totalCells / 8000);

            try
            {
                for (int barIndex = firstBar; barIndex <= lastBar; barIndex += stride)
                {
                    int column = barIndex - model.StartIndex;
                    if (column < 0 || column >= model.Bars)
                        continue;

                    float cellLeft = chartControl.GetXByBarIndex(ChartBars, barIndex);
                    float cellRight = chartControl.GetXByBarIndex(ChartBars, barIndex + 1);
                    if (cellRight < ChartPanel.X || cellLeft > ChartPanel.X + ChartPanel.W)
                        continue;
                    float cellWidth = Math.Max(1f, cellRight - cellLeft);

                    for (int bin = 0; bin < model.Bins; bin++)
                    {
                        double value = model.Matrix[layer, bin, column];
                        if (value == 0)
                            continue;

                        byte r, g, b;
                        double intensity;
                        if (layer == (int)LiquidityLayer.DeltaPressure)
                        {
                            double magnitude = Math.Min(1.0, Math.Abs(value) / max);
                            intensity = Math.Pow(magnitude, 0.6);
                            if (value >= 0)
                                HeatRamp(intensity, out r, out g, out b);
                            else
                                CoolRamp(intensity, out r, out g, out b);
                        }
                        else
                        {
                            double magnitude = Math.Min(1.0, value / max);
                            intensity = Math.Pow(magnitude, 0.5);
                            HeatRamp(intensity, out r, out g, out b);
                        }

                        float binTop = chartScale.GetYByValue(model.PriceLow + (bin + 1) * model.BinSize);
                        float binBottom = chartScale.GetYByValue(model.PriceLow + bin * model.BinSize);
                        float cellHeight = binBottom - binTop;
                        if (cellHeight < 1f || binBottom < ChartPanel.Y || binTop > ChartPanel.Y + ChartPanel.H)
                            continue;

                        SetHeatCellBrush(r, g, b, (float)(intensity * opacity));
                        if (heatCellBrush == null)
                            return;

                        RenderTarget.FillRectangle(new SharpDX.RectangleF(
                            cellLeft, binTop, cellWidth, cellHeight), heatCellBrush);
                    }
                }
            }
            catch (Exception)
            {
                // the render target can be lost during a chart resize; skip this frame
            }
            finally
            {
                if (heatCellBrush != null)
                {
                    heatCellBrush.Dispose();
                    heatCellBrush = null;
                }
            }
        }

        private void SetHeatCellBrush(byte r, byte g, byte b, float alpha)
        {
            if (heatCellBrush != null && heatCellR == r && heatCellG == g && heatCellB == b)
                return;

            if (heatCellBrush != null)
            {
                heatCellBrush.Dispose();
                heatCellBrush = null;
            }

            heatCellR = r;
            heatCellG = g;
            heatCellB = b;
            heatCellBrush = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget,
                new SharpDX.Color4(r / 255f, g / 255f, b / 255f, alpha));
        }

        private static void HeatRamp(double t, out byte r, out byte g, out byte b)
        {
            t = Clamp01(t);
            if (t < 0.30)
                Blend(1, 105, 111, 67, 122, 34, t / 0.30, out r, out g, out b);
            else if (t < 0.55)
                Blend(67, 122, 34, 196, 66, 25, (t - 0.30) / 0.25, out r, out g, out b);
            else if (t < 0.80)
                Blend(196, 66, 25, 209, 99, 167, (t - 0.55) / 0.25, out r, out g, out b);
            else
                Blend(209, 99, 167, 255, 214, 102, (t - 0.80) / 0.20, out r, out g, out b);
        }

        private static void CoolRamp(double t, out byte r, out byte g, out byte b)
        {
            t = Clamp01(t);
            if (t < 0.45)
                Blend(49, 59, 59, 161, 44, 123, t / 0.45, out r, out g, out b);
            else
                Blend(161, 44, 123, 236, 62, 122, (t - 0.45) / 0.55, out r, out g, out b);
        }

        private static void Blend(int r1, int g1, int b1, int r2, int g2, int b2, double t,
            out byte r, out byte g, out byte b)
        {
            t = Clamp01(t);
            r = (byte)Math.Round(r1 + (r2 - r1) * t);
            g = (byte)Math.Round(g1 + (g2 - g1) * t);
            b = (byte)Math.Round(b1 + (b2 - b1) * t);
        }

        private static double Clamp01(double value)
        {
            return value < 0 ? 0 : (value > 1 ? 1 : value);
        }

        #endregion

        #region Chart levels and summary

        private void DrawLevelsAndSummary(HeatModel m)
        {
            EnsureResources();

            int poolLabels = ShowPools ? Math.Min(MaxPoolsShown, m.Pools.Count) : 0;
            for (int i = 0; i < poolLabels; i++)
            {
                LiquidityPool pool = m.Pools[i];
                System.Windows.Media.Brush brush = pool.Side == LiquiditySide.BuySide ? brushPoolAbove : brushPoolBelow;
                Draw.HorizontalLine(this, PoolTagPrefix + i.ToString(Inv), pool.Price, brush, DashStyleHelper.Dot, 2);
                string poolText = string.Format(Inv, "{0} {1} x{2}{3}",
                    pool.Side == LiquiditySide.BuySide ? "buy" : "sell",
                    FormatPrice(pool.Price, m),
                    pool.Touches,
                    pool.Sweeps > 0 ? " swept " + pool.Sweeps.ToString(Inv) : string.Empty);
                Draw.Text(this, PoolTextTagPrefix + i.ToString(Inv), false, poolText, 1, pool.Price,
                    0, brush, labelFont, System.Windows.TextAlignment.Left,
                    System.Windows.Media.Brushes.Transparent, System.Windows.Media.Brushes.Transparent, 0);
            }
            ClearStaleLabels(PoolTagPrefix, poolLabels, previousPoolLabels);
            ClearStaleLabels(PoolTextTagPrefix, poolLabels, previousPoolLabels);
            previousPoolLabels = poolLabels;

            int roundLabels = ShowRoundNumbers ? Math.Min(6, m.Rounds.Count) : 0;
            for (int i = 0; i < roundLabels; i++)
            {
                RoundLevel level = m.Rounds[i];
                Draw.HorizontalLine(this, RoundTagPrefix + i.ToString(Inv), level.Price, brushRound,
                    level.Major ? DashStyleHelper.Solid : DashStyleHelper.Dash, level.Major ? 2 : 1);
            }
            ClearStaleLabels(RoundTagPrefix, roundLabels, previousRoundLabels);
            previousRoundLabels = roundLabels;

            int sweepLabels = 0;
            if (ShowSweeps && MaxSweepMarkers > 0 && m.Sweeps.Count > 0)
            {
                int first = Math.Max(0, m.Sweeps.Count - MaxSweepMarkers);
                for (int i = first; i < m.Sweeps.Count; i++)
                {
                    SweepMark mark = m.Sweeps[i];
                    int barsAgo = (m.StartIndex + m.Bars - 1) - mark.BarIndex;
                    if (barsAgo < 0)
                        continue;
                    System.Windows.Media.Brush brush = mark.Side == LiquiditySide.BuySide ? brushSweepBuy : brushSweepSell;
                    Draw.Diamond(this, SweepTagPrefix + sweepLabels.ToString(Inv), false, barsAgo, mark.Price, brush);
                    sweepLabels++;
                }
            }
            ClearStaleLabels(SweepTagPrefix, sweepLabels, previousSweepMarks);
            previousSweepMarks = sweepLabels;

            if (ShowSessionLevels)
            {
                if (m.PriorHigh > 0)
                    Draw.HorizontalLine(this, "LH_PDH", m.PriorHigh, brushLevel, DashStyleHelper.Dash, 1);
                else
                    RemoveDrawObject("LH_PDH");
                if (m.PriorLow > 0)
                    Draw.HorizontalLine(this, "LH_PDL", m.PriorLow, brushLevel, DashStyleHelper.Dash, 1);
                else
                    RemoveDrawObject("LH_PDL");
                Draw.HorizontalLine(this, "LH_ORH", m.OpeningHigh, brushLevel, DashStyleHelper.Dot, 1);
                Draw.HorizontalLine(this, "LH_ORL", m.OpeningLow, brushLevel, DashStyleHelper.Dot, 1);
                Draw.HorizontalLine(this, "LH_VWAP", m.Vwap, brushVoid, DashStyleHelper.Dash, 2);
            }
            else
            {
                RemoveDrawObject("LH_PDH");
                RemoveDrawObject("LH_PDL");
                RemoveDrawObject("LH_ORH");
                RemoveDrawObject("LH_ORL");
                RemoveDrawObject("LH_VWAP");
            }

            DrawLevelNamesAndArrows(m);

            if (ShowVoids && m.Voids.Count > 0)
                Draw.HorizontalLine(this, VoidTag, m.Voids[0].Center, brushVoid, DashStyleHelper.Dash, 1);

            if (ShowSummary)
                Draw.TextFixed(this, SummaryTag, BuildSummaryText(m), TextPosition.TopRight,
                    brushText, labelFont, System.Windows.Media.Brushes.Transparent,
                    System.Windows.Media.Brushes.Transparent, 0);
        }

        private void DrawLevelNamesAndArrows(HeatModel m)
        {
            // Reuse tags at the latest completed candle, without changing chart scale.
            // Stagger nearby labels in pixels; connectors retain the exact level price.
            bool wantTags = ShowLevelTags || ShowLiveArrows;
            List<KeyValuePair<string, double>> rows = wantTags
                ? CollectLevelRows(m) : new List<KeyValuePair<string, double>>();
            int wanted = rows.Count > 16 ? 16 : rows.Count;

            for (int i = 0; i < wanted; i++)
            {
                string tag = LevelNamePrefix + i.ToString(Inv);
                string arrowTag = LiveArrowPrefix + i.ToString(Inv);
                double price = rows[i].Value;
                string text = rows[i].Key + " " + FormatPrice(price, m);
                System.Windows.Media.Brush brush = BrushForLevel(rows[i].Key);

                string lineTag = tag + "_Line";
                if (ShowLevelTags)
                {
                    int offset = 8 + (i % 3) * (TextFontSize + 3);
                    Draw.Text(this, tag, false, text, 3, price, offset, brush, labelFont,
                        System.Windows.TextAlignment.Right,
                        System.Windows.Media.Brushes.Transparent,
                        System.Windows.Media.Brushes.Black, 65);
                    Draw.Line(this, lineTag, false, 3, price, 0, price,
                        brush, DashStyleHelper.Solid, 1);
                }
                else
                {
                    RemoveDrawObject(tag);
                    RemoveDrawObject(lineTag);
                }

                // Remove first because the same tag may change arrow direction.
                RemoveDrawObject(arrowTag);
                if (ShowLiveArrows)
                {
                    bool above = price >= m.Price;
                    if (above)
                        Draw.ArrowDown(this, arrowTag, false, 0,
                            price + m.TickSize, brush);
                    else
                        Draw.ArrowUp(this, arrowTag, false, 0,
                            price - m.TickSize, brush);
                }
                else
                {
                    RemoveDrawObject(arrowTag);
                }
            }

            // wipe anything the current frame did not redraw
            for (int i = wanted; i < previousLevelRows; i++)
            {
                RemoveDrawObject(LevelNamePrefix + i.ToString(Inv));
                RemoveDrawObject(LevelNamePrefix + i.ToString(Inv) + "_Line");
                RemoveDrawObject(LiveArrowPrefix + i.ToString(Inv));
            }
            previousLevelRows = wanted;
        }

        private int LadderPocBinModel(HeatModel m)
        {
            int best = -1;
            double maximum = 0;
            for (int b = 0; b < m.Bins; b++)
            {
                double value = LadderMetricChoice == LadderMetric.TradedVolume
                    ? m.Profile[b].Volume
                    : LadderMetricChoice == LadderMetric.DeltaPressure
                        ? Math.Abs(m.DeltaOf(b)) : m.RestingOf(b);
                if (value > maximum)
                {
                    maximum = value;
                    best = b;
                }
            }
            return best;
        }

        private List<KeyValuePair<string, double>> CollectLevelRows(HeatModel m)
        {
            List<KeyValuePair<string, double>> rows = new List<KeyValuePair<string, double>>();
            double minGap = Math.Max(m.BinSize, m.TickSize) * 1.5;

            int pocBin = LadderPocBinModel(m);
            if (pocBin >= 0)
                AddLevelRow(rows, "POC", m.BinCenter(pocBin), minGap);
            if (m.NodePrices.Count > 0)
                AddLevelRow(rows, "HVN", m.NodePrices[0], minGap);
            if (m.Voids.Count > 0)
                AddLevelRow(rows, "LVN", m.Voids[0].Center, minGap);

            foreach (LiquidityPool pool in m.Pools.Where(p => ShowSweeps && p.Sweeps > 0).Take(6))
            {
                string name = pool.Kind == PoolKind.High ? "SWEEP-H" : "SWEEP-L";
                AddLevelRow(rows, name, pool.Price, minGap);
            }

            if (ShowSessionLevels)
            {
                AddLevelRow(rows, "PDH", m.PriorHigh, minGap);
                AddLevelRow(rows, "PDL", m.PriorLow, minGap);
                AddLevelRow(rows, "ORH", m.OpeningHigh, minGap);
                AddLevelRow(rows, "ORL", m.OpeningLow, minGap);
                AddLevelRow(rows, "VWAP", m.Vwap, minGap);
                AddLevelRow(rows, "WH", m.WeekHigh, minGap);
                AddLevelRow(rows, "WL", m.WeekLow, minGap);
            }

            rows.Sort((a, b) => b.Value.CompareTo(a.Value));
            return rows;
        }

        private static void AddLevelRow(List<KeyValuePair<string, double>> rows,
            string name, double price, double minGap)
        {
            if (double.IsNaN(price) || double.IsInfinity(price) || price <= 0)
                return;
            foreach (KeyValuePair<string, double> row in rows)
            {
                if (row.Key == name && Math.Abs(row.Value - price) < minGap)
                    return;
            }
            rows.Add(new KeyValuePair<string, double>(name, price));
        }

        private System.Windows.Media.Brush BrushForLevel(string name)
        {
            if (name == "POC")
                return MakeBrush(255, 214, 102);
            if (name == "HVN")
                return brushLevel;
            if (name == "LVN")
                return brushVoid;
            if (name == "PDH" || name == "PDL")
                return brushLevel;
            if (name == "VWAP")
                return brushVoid;
            if (name.StartsWith("SWEEP", StringComparison.Ordinal))
                return brushSweepSell;
            if (name == "ORH" || name == "ORL" || name == "WH" || name == "WL")
                return brushRound;
            return brushText;
        }

        private void ClearStaleLabels(string prefix, int current, int previous)
        {
            for (int i = current; i < previous; i++)
                RemoveDrawObject(prefix + i.ToString(Inv));
        }

        private string BuildSummaryText(HeatModel m)
        {
            StringBuilder sb = new StringBuilder();
            sb.AppendLine("LIQUIDITY HEATMAP  " + Instrument.MasterInstrument.Name
                        + "  " + BarsPeriod.Value + " " + BarsPeriod.BarsPeriodType);
            sb.AppendLine("Bias: " + m.Bias + "   Delta: "
                        + (m.DeltaBias * 100).ToString("+0.0;-0.0", Inv) + "%");
            sb.AppendLine("Above: " + DescribePool(NearestPool(m, true), m));
            sb.AppendLine("Below: " + DescribePool(NearestPool(m, false), m));

            if (m.NodePrices.Count > 0 || m.Voids.Count > 0)
                sb.AppendLine("HVN " + (m.NodePrices.Count > 0 ? FormatPrice(m.NodePrices[0], m) : "-")
                            + "   Void " + (m.Voids.Count > 0
                                ? FormatPrice(m.Voids[0].Low, m) + "-" + FormatPrice(m.Voids[0].High, m)
                                : "-"));
            sb.AppendLine("PDH/PDL " + FormatPrice(m.PriorHigh, m) + "/" + FormatPrice(m.PriorLow, m)
                        + "   VWAP " + FormatPrice(m.Vwap, m));
            return sb.ToString();
        }

        private string DescribePool(LiquidityPool pool, HeatModel m)
        {
            if (pool == null)
                return "none";
            return FormatPrice(pool.Price, m) + "  x" + pool.Touches
                 + "  swept " + pool.Sweeps
                 + "  (" + FormatTicks(pool.Distance, m) + " ticks)";
        }

        private LiquidityPool NearestPool(HeatModel m, bool above)
        {
            LiquidityPool best = null;
            double bestDistance = double.MaxValue;
            double minGap = Math.Max(m.BinSize, m.TickSize) * 0.5;
            foreach (LiquidityPool pool in m.Pools)
            {
                if ((pool.Price > m.Price) != above)
                    continue;
                double distance = Math.Abs(pool.Distance);
                if (distance < minGap)
                    continue;                       // level sitting inside the current bar
                if (distance < bestDistance)
                {
                    bestDistance = distance;
                    best = pool;
                }
            }
            return best;
        }

        private string FormatPrice(double value, HeatModel m)
        {
            int decimals = m.TickSize >= 0.01 ? 2 : (m.TickSize >= 0.001 ? 3 : 5);
            return value.ToString("N" + decimals.ToString(Inv), Inv);
        }

        private string FormatTicks(double distance, HeatModel m)
        {
            if (m.TickSize <= 0)
                return distance.ToString("F2", Inv);
            return (distance / m.TickSize).ToString("+0;-0", Inv);
        }

        #endregion

        #region Helpers

        private void EnsureResources()
        {
            if (resourcesReady)
                return;

            brushPoolAbove = MakeBrush(34, 160, 173);
            brushPoolBelow = MakeBrush(209, 99, 167);
            brushSweepBuy = MakeBrush(109, 170, 69);
            brushSweepSell = MakeBrush(236, 62, 122);
            brushRound = MakeBrush(151, 150, 146);
            brushVoid = MakeBrush(85, 145, 199);
            brushLevel = MakeBrush(187, 101, 59);
            brushText = MakeBrush(205, 204, 202);
            labelFont = new SimpleFont("Arial", TextFontSize);
            resourcesReady = true;
        }

        private static System.Windows.Media.Brush MakeBrush(byte r, byte g, byte b)
        {
            SolidColorBrush brush = new SolidColorBrush(System.Windows.Media.Color.FromRgb(r, g, b));
            brush.Freeze();
            return brush;
        }

        private double[] ParseLeverages(string text)
        {
            List<double> values = new List<double>();
            if (!string.IsNullOrEmpty(text))
            {
                foreach (string part in text.Split(','))
                {
                    double value;
                    if (double.TryParse(part.Trim(), NumberStyles.Any, Inv, out value) && value > 1)
                        values.Add(value);
                }
            }
            if (values.Count == 0)
                values.AddRange(new double[] { 10, 20, 50, 100 });
            values.Sort();
            return values.ToArray();
        }

        private double HighAt(int index)
        {
            return High[GetBarsAgo(index)];
        }

        private double LowAt(int index)
        {
            return Low[GetBarsAgo(index)];
        }

        private double OpenAt(int index)
        {
            return Open[GetBarsAgo(index)];
        }

        private double CloseAt(int index)
        {
            return Close[GetBarsAgo(index)];
        }

        private double VolumeAt(int index)
        {
            return (double)Volume[GetBarsAgo(index)];
        }

        private DateTime TimeAt(int index)
        {
            return Time[GetBarsAgo(index)];
        }

        /// <summary>
        /// Converts an absolute bar index into the BarsAgo offset NT8 series
        /// indexers expect. Clamped so diagnostics never throw.
        /// </summary>
        private int GetBarsAgo(int index)
        {
            int barsAgo = CurrentBar - index;
            if (barsAgo < 0)
                return 0;
            if (barsAgo > CurrentBar)
                return CurrentBar;
            return barsAgo;
        }

        #endregion
    }
}
