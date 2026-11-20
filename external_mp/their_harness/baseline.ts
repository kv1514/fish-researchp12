// Their own code, their own rules: establish the reference before building anything.
import { decide, hashSeed, newGame, reduce } from '../lib/engine/index.ts'
import { seatView } from '../lib/engine/index.ts'
import { ALL_BOOKS } from '../lib/engine/index.ts'
import type { BotDifficulty, Seat } from '../lib/engine/index.ts'

const N = Number(process.argv[2] ?? 100)
const A = (process.argv[3] ?? 'hard') as BotDifficulty
const B = (process.argv[4] ?? 'hard') as BotDifficulty

let aw = 0, bw = 0, ties = 0, voids = 0, illegal = 0, capped = 0, moves = 0
for (let i = 0; i < N; i++) {
  const seed = `sim-${A}-vs-${B}-${i}`
  let state = newGame(seed, undefined, (i % 6) as Seat)
  let steps = 0
  while (state.phase !== 'finished' && steps < 5000) {
    const diff = state.turn % 2 === 0 ? A : B
    const action = decide(seatView(state, state.turn), diff, hashSeed(`${seed}:${state.moveIndex}`)())
    const r = reduce(state, action)
    if (!r.ok) { illegal++; break }
    state = r.state; steps++
  }
  moves += steps
  if (state.phase !== 'finished') { capped++; continue }
  for (const bk of ALL_BOOKS) if (state.books[bk]?.outcome === 'void') voids++
  if (state.score[0] > state.score[1]) aw++
  else if (state.score[1] > state.score[0]) bw++
  else ties++
}
console.log(JSON.stringify({ N, A, B, aWins: aw, bWins: bw, ties, voids, illegal, capped,
  avgMoves: +(moves / N).toFixed(1),
  aWinPctOfDecided: aw + bw ? +(100 * aw / (aw + bw)).toFixed(1) : null }))
