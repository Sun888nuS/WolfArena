import { useMemo, useState } from "react";

import type { GameSnapshot, PublicPlayer } from "../../types/game";
import {
  alignmentLabel,
  buildReviewTimeline,
  deathReasonLabel,
  eventTypeLabel,
  filterReviewItems,
  hasForcedFinish,
  phaseLabel,
  roleLabel,
  type ReviewTab,
  winnerLabel,
} from "./reviewFormat";
import "./review.css";

interface GameReviewDialogProps {
  snapshot: GameSnapshot;
  playersById: Map<string, PublicPlayer>;
  onClose: () => void;
}

const REVIEW_TABS: { key: ReviewTab; label: string }[] = [
  { key: "timeline", label: "完整流程" },
  { key: "night", label: "夜晚行动" },
  { key: "speeches", label: "发言记录" },
  { key: "votes", label: "投票记录" },
  { key: "roles", label: "身份总览" },
];

export function GameReviewDialog({
  snapshot,
  playersById,
  onClose,
}: GameReviewDialogProps) {
  const [tab, setTab] = useState<ReviewTab>("timeline");
  const reviewEvents = snapshot.review_events?.length ? snapshot.review_events : snapshot.events;
  const timelineItems = useMemo(
    () => buildReviewTimeline(reviewEvents, playersById),
    [playersById, reviewEvents],
  );
  const activeItems = tab === "roles" ? [] : filterReviewItems(timelineItems, tab);
  const forcedFinish = hasForcedFinish(reviewEvents);

  return (
    <div className="review-page-overlay" role="dialog" aria-modal="true" aria-labelledby="review-title">
      <section className="review-page">
        <header className="review-page-header">
          <div>
            <span>游戏复盘</span>
            <strong id="review-title">本局复盘</strong>
          </div>
          <button className="review-close-button" type="button" onClick={onClose} aria-label="关闭复盘">
            ×
          </button>
        </header>

        <div className="review-summary">
          <div>
            <span>结果</span>
            <strong>{forcedFinish ? "玩家手动结束" : `${winnerLabel(snapshot.winner)}获胜`}</strong>
          </div>
          <div>
            <span>轮次</span>
            <strong>第 {snapshot.round_no} 轮</strong>
          </div>
          <div>
            <span>记录</span>
            <strong>{timelineItems.length} 条</strong>
          </div>
        </div>

        {forcedFinish ? (
          <div className="review-notice">玩家手动结束对局，以下展示当前已有事件记录。</div>
        ) : null}

        <nav className="review-page-tabs" aria-label="复盘视图">
          {REVIEW_TABS.map((item) => (
            <button
              className={tab === item.key ? "active" : ""}
              key={item.key}
              onClick={() => setTab(item.key)}
              type="button"
            >
              {item.label}
            </button>
          ))}
        </nav>

        {tab === "roles" ? (
          <ReviewRoster snapshot={snapshot} />
        ) : (
          <div className="review-page-list">
            {activeItems.length === 0 ? <div className="review-page-empty">暂无复盘记录</div> : null}
            {activeItems.map(({ event, index, description }) => (
              <article className="review-page-item" key={`${event.type}-${index}`}>
                <span>
                  第 {event.round_no} 轮 · {phaseLabel(event.phase)} · {eventTypeLabel(event.type)}
                </span>
                <strong>{event.actor_id ? playerLabel(event.actor_id, playersById) : "系统"}</strong>
                <p>{description}</p>
              </article>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

function ReviewRoster({ snapshot }: { snapshot: GameSnapshot }) {
  return (
    <div className="review-roster-grid">
      {snapshot.players
        .slice()
        .sort((left, right) => left.seat - right.seat)
        .map((player) => (
          <article className="review-roster-card" key={player.player_id}>
            <div>
              <strong>
                {player.seat} 号 {player.name}
              </strong>
              <span>{player.is_human ? "真人玩家" : "AI 玩家"}</span>
            </div>
            <p>
              {roleLabel(player.role ?? "")} · {alignmentLabel(player.alignment ?? "")}
            </p>
            <small>
              {player.alive
                ? "存活"
                : `出局${player.dead_reason ? `（${deathReasonLabel(player.dead_reason)}）` : ""}`}
            </small>
          </article>
        ))}
    </div>
  );
}

function playerLabel(playerId: string, playersById: Map<string, PublicPlayer>): string {
  const player = playersById.get(playerId);
  return player ? `${player.seat} 号 ${player.name}` : playerId || "无";
}
