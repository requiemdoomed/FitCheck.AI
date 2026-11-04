// Numeric helpers that make the browser engine round and sum exactly like
// the Python reference (CPython 3.12+).

// Python's round(): decides on the exact decimal value of the double, and
// rounds exact halves to even (0.8125 -> 0.812). toFixed(60) gives that exact
// expansion; toFixed(n) already rounds non-ties correctly.
export const pyRound = (x, n) => {
  const exact = Math.abs(x).toFixed(60);
  const dot = exact.indexOf(".");
  const rest = exact.slice(dot + 1 + n);
  if (/^50*$/.test(rest)) {
    const f = 10 ** n;
    const fl = Math.floor(Math.abs(x) * f);
    return (Math.sign(x) * (fl % 2 === 0 ? fl : fl + 1)) / f;
  }
  return Number(x.toFixed(n));
};
// Python 3.12+ sum() over floats uses Neumaier compensated summation;
// match it so stored values round identically.
export function pySum(xs) {
  let sum = 0;
  let c = 0;
  for (const x of xs) {
    const t = sum + x;
    c += Math.abs(sum) >= Math.abs(x) ? (sum - t) + x : (x - t) + sum;
    sum = t;
  }
  return sum + c;
}

