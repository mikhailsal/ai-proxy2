import { useCallback, useEffect, useRef, useState } from 'react';

function findScrollParent(el: HTMLElement | null): HTMLElement | null {
  let cur = el;
  while (cur) { const s = getComputedStyle(cur).overflowY; if (s === 'auto' || s === 'scroll') return cur; cur = cur.parentElement; }
  return null;
}

export function useBranchVisibility(branchCount: number, containerRef: React.RefObject<HTMLElement | null>) {
  const sentinelRefs = useRef<(HTMLElement | null)[]>([]);
  const contentRefs = useRef<(HTMLElement | null)[]>([]);
  const [visible, setVisible] = useState<boolean[]>(() => Array(branchCount).fill(true));
  const visRef = useRef<boolean[]>(Array(branchCount).fill(true));
  const heightsRef = useRef<number[]>(Array(branchCount).fill(0));
  const [heights, setHeights] = useState<number[]>(() => Array(branchCount).fill(0));
  const setSentinelRef = useCallback((i: number, el: HTMLElement | null) => { sentinelRefs.current[i] = el; }, []);
  const setContentRef = useCallback((i: number, el: HTMLElement | null) => { contentRefs.current[i] = el; }, []);

  useEffect(() => {
    const scroll = findScrollParent(containerRef.current);
    if (!scroll || typeof IntersectionObserver === 'undefined') return;
    const measureHeights = () => {
      let changed = false;
      for (let i = 0; i < branchCount; i++) {
        const el = contentRefs.current[i];
        if (!el || !visRef.current[i]) continue;
        const h = el.scrollHeight;
        if (h > 0 && h !== heightsRef.current[i]) { heightsRef.current[i] = h; changed = true; }
      }
      if (changed) setHeights([...heightsRef.current]);
    };
    let debounceTimer: ReturnType<typeof setTimeout> | null = null;
    let pendingNext: boolean[] | null = null;
    const applyCollapse = () => {
      debounceTimer = null;
      if (pendingNext) { visRef.current = pendingNext; setVisible([...pendingNext]); pendingNext = null; }
    };
    const observer = new IntersectionObserver((entries) => {
      const next = [...visRef.current];
      let changed = false;
      for (const entry of entries) {
        const idx = sentinelRefs.current.indexOf(entry.target as HTMLElement);
        if (idx === -1) continue;
        const isVis = entry.isIntersecting || entry.intersectionRatio > 0;
        if (next[idx] !== isVis) { next[idx] = isVis; changed = true; }
      }
      if (!changed) return;
      if (next.filter(Boolean).length > visRef.current.filter(Boolean).length) {
        if (debounceTimer) { clearTimeout(debounceTimer); debounceTimer = null; }
        pendingNext = null;
        visRef.current = next;
        setVisible([...next]);
      } else {
        pendingNext = next;
        if (!debounceTimer) debounceTimer = setTimeout(applyCollapse, 250);
      }
    }, { root: scroll, rootMargin: '100px 0px 100px 0px', threshold: 0 });
    for (let i = 0; i < branchCount; i++) { const el = sentinelRefs.current[i]; if (el) observer.observe(el); }
    const t1 = setTimeout(measureHeights, 200);
    const t2 = setTimeout(measureHeights, 1000);
    const ro = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(() => measureHeights()) : null;
    for (let i = 0; i < branchCount; i++) { const el = contentRefs.current[i]; if (el) ro?.observe(el); }
    return () => { observer.disconnect(); ro?.disconnect(); clearTimeout(t1); clearTimeout(t2); if (debounceTimer) clearTimeout(debounceTimer); };
  }, [branchCount, containerRef]);

  return { visible, setSentinelRef, setContentRef, heights };
}
