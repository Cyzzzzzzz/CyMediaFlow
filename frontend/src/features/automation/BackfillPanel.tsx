import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { featureApi } from "./featureApi";

export function BackfillPanel({
  ruleId,
  onOffset,
}: {
  ruleId: number;
  onOffset: (value: number) => void;
}) {
  const client = useQueryClient();
  const [selected, setSelected] = useState<number[]>([]);
  const preview = useMutation({
    mutationFn: () => featureApi.backfill(ruleId),
    onSuccess: () => setSelected([]),
  });
  const collect = useMutation({
    mutationFn: () => featureApi.collect(ruleId, selected),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["automation"] });
      preview.mutate();
    },
  });
  return (
    <details className="subscription-section">
      <summary>缺集补全与偏移建议</summary>
      <div className="subscription-section-body">
        <p className="automation-note">
          按已保存规则核对本地文件、在途任务与历史发布。可先在高级设置填写总集数。
        </p>
        <button
          className="secondary-button"
          disabled={preview.isPending}
          onClick={() => preview.mutate()}
        >
          检查缺集
        </button>
        {preview.data ? (
          <>
            <p className="automation-note">
              本地 {preview.data.local.length} 集，已提交{" "}
              {preview.data.queued.length} 集。
              {!preview.data.expected_known
                ? "总集数未知，只检查已发现的集号范围。"
                : ""}
            </p>
            <div className="automation-actions">
              <button
                className="quiet-button"
                onClick={() =>
                  setSelected(
                    preview.data!.missing.flatMap((m) =>
                      m.candidate ? [m.candidate.release_id] : [],
                    ),
                  )
                }
              >
                选择全部可补集
              </button>
              <button className="quiet-button" onClick={() => setSelected([])}>
                清空
              </button>
            </div>
            {preview.data.missing.map((m) => (
              <label className="automation-check" key={m.episode}>
                <input
                  type="checkbox"
                  disabled={!m.candidate}
                  checked={
                    !!m.candidate && selected.includes(m.candidate.release_id)
                  }
                  onChange={(e) =>
                    setSelected((old) =>
                      e.target.checked
                        ? [...old, m.candidate!.release_id]
                        : old.filter((id) => id !== m.candidate!.release_id),
                    )
                  }
                />
                <span>
                  E{m.episode} ·{" "}
                  {m.candidate?.title ?? "没有可用候选，可在资源搜索中寻找"}
                </span>
              </label>
            ))}
            {!preview.data.missing.length ? <p>当前范围没有缺集。</p> : null}
            <button
              className="primary-button"
              disabled={!selected.length || collect.isPending}
              onClick={() => collect.mutate()}
            >
              下载所选 {selected.length} 集
            </button>
            {preview.data.offset_suggestion ? (
              <p className="automation-note">
                {preview.data.offset_suggestion.reason}
                <button
                  className="quiet-button"
                  onClick={() =>
                    onOffset(preview.data!.offset_suggestion!.episode_offset)
                  }
                >
                  填写建议偏移 {preview.data.offset_suggestion.episode_offset}
                  （需保存）
                </button>
              </p>
            ) : null}
          </>
        ) : null}
        {preview.error || collect.error ? (
          <p role="alert" className="automation-note error">
            {(preview.error ?? collect.error)?.message}
          </p>
        ) : null}
      </div>
    </details>
  );
}
