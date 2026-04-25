import json
from collections import Counter

spikes = []
worst_counts = Counter()
total_frames = 0
sums = Counter()
maxes = {}

with open("hex_colony_perf.jsonl", encoding="utf-8") as f:
    for line in f:
        try:
            d = json.loads(line)
        except Exception:
            continue
        if "frame_ms" not in d:
            continue
        total_frames += 1
        fm = d["frame_ms"]
        worst = d.get("worst", "?")
        if fm > 50:
            spikes.append((d["t"], fm, worst, d["sections"].get(worst, 0), d.get("frame_index", 0)))
            worst_counts[worst] += 1
        for k, v in d.get("sections", {}).items():
            sums[k] += v
            if v > maxes.get(k, 0):
                maxes[k] = v

print(f"Total frames: {total_frames}")
print(f"Spikes (>50ms): {len(spikes)}")
print(f"Worst-section counts among spikes: {worst_counts.most_common()}")
print(f"\nTop section means (ms): ")
for k, v in sorted(sums.items(), key=lambda x: -x[1])[:15]:
    print(f"  {k}: mean={v/total_frames:.3f} max={maxes.get(k,0):.1f}")

print(f"\nFirst 20 spikes:")
for s in spikes[:20]:
    print(f"  t={s[0]:.1f}s idx={s[4]} frame={s[1]:.1f}ms worst={s[2]} ({s[3]:.1f}ms)")
print(f"\nLast 20 spikes:")
for s in spikes[-20:]:
    print(f"  t={s[0]:.1f}s idx={s[4]} frame={s[1]:.1f}ms worst={s[2]} ({s[3]:.1f}ms)")
