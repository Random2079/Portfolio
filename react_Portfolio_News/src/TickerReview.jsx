import { useMemo } from "react";
import { motion } from "framer-motion";
import PositionCard, { posCardFromHoldings } from "./PositionCard";
import PriceChart from "./PriceChart";
import ReviewPanel from "./ReviewPanel";
import "./TickerReview.css";

/**
 * R2 panel: position card + LWC chart + KS review for selected ticker.
 * Layout denser / flatter like vanilla chart-box stack.
 */
export default function TickerReview({ ticker, holdings, totalValue }) {
  const tid = String(ticker || "")
    .trim()
    .toUpperCase();

  const localAvg = useMemo(() => {
    const local = posCardFromHoldings(tid, holdings, totalValue);
    return local?.avg_price ?? null;
  }, [tid, holdings, totalValue]);

  if (!tid) return null;

  return (
    <motion.section
      className="ticker-review"
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.28, ease: [0.22, 1, 0.36, 1] }}
    >
      <div className="review-head">
        <h2>Разбор бумаги</h2>
        <p className="lead">
          {tid} · карточка · график · сверка KS
        </p>
      </div>

      <PriceChart ticker={tid} holdings={holdings} avgPrice={localAvg} />
      <PositionCard
        ticker={tid}
        holdings={holdings}
        totalValue={totalValue}
      />
      <ReviewPanel ticker={tid} />
    </motion.section>
  );
}
