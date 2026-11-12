
import random, time
random.seed(7)
pts = [(random.gauss(cx, 1), random.gauss(cy, 1)) for cx, cy in [(0, 0), (8, 8), (0, 8)] for _ in range(200)]
cent = random.sample(pts, 3)
print(f"k-means: {len(pts)} points, k=3", flush=True)
for it in range(1, 16):
    groups = [[] for _ in cent]
    for p in pts:
        groups[min(range(3), key=lambda i: (p[0]-cent[i][0])**2 + (p[1]-cent[i][1])**2)].append(p)
    cent = [(sum(x for x, _ in g)/len(g), sum(y for _, y in g)/len(g)) for g in groups]
    print(f"iter {it:2d}  " + "  ".join(f"({x:.1f},{y:.1f})" for x, y in cent), flush=True)
    time.sleep(1)
print("done")
