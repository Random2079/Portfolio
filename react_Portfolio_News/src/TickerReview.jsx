import { useMemo } from "react";
import { motion } from "framer-motion";
import PositionCard, { posCardFromHoldings } from "./PositionCard";
import PriceChart from "./PriceChart";
import ReviewPanel from "./ReviewPanel";

/**
 * R2 panel: position card + LWC chart + KS review for selected ticker.
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
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
    >
      <div className="review-head">
        <h2>Разбор · {tid}</h2>
        <p className="muted">карточка · график · сверка KS</p>
      </div>
      <div className="review-layout">
        <div className="review-main">
          <PositionCard
            ticker={tid}
            holdings={holdings}
            totalValue={totalValue}
          />
          <PriceChart
            ticker={tid}
            holdings={holdings}
            avgPrice={localAvg}
          />
        </div>
        <ReviewPanel ticker={tid} />
      </div>
    </motion.section>
  );
}
