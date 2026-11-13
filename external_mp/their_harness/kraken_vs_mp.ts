/**
 * KRAKEN vs the Canadian-Fish-Demo bots, inside THEIR engine.
 *
 * Their reducer arbitrates, their seatView projects, their decide() plays one
 * team. Ours plays the other through a line-protocol subprocess. The loop and
 * the seeding are copied from their own scripts/simulate-main.ts so the
 * comparison is against the baseline their harness reports, not a new one:
 * seats 0/2/4 = team A, 1/3/5 = team B, seeds `sim-{pairing}-{i}`, starting
 * seat rotates i%6, decide() seeded hash(`${seed}:${moveIndex}`).
 *
 * --side a|b  which team KRAKEN plays (both are run; first-move advantage and
 *             any seat asymmetry then cancel in the pooled figure).
 */
import { decide, hashSeed, newGame, reduce } from '../lib/engine/index.ts'
import { seatView } from '../lib/engine/index.ts'
import { ALL_BOOKS } from '../lib/engine/index.ts'
import type { BotDifficulty, GameState, Seat } from '../lib/engine/index.ts'
import { spawn } from 'node:child_process'
import { createInterface } from 'node:readline'

const N = Number(process.env.N ?? 100)
const THEIRS = (process.env.THEIRS ?? 'hard') as BotDifficulty
const SPEC = process.env.SPEC ?? 'KRAKEN_V1'
const PYREPO = process.env.PYREPO ?? '/home/user/fish-researchp12'

const py = spawn('python3', ['-u', 'external_mp/serve.py', '--spec', SPEC], {
  cwd: PYREPO, stdio: ['pipe', 'pipe', 'inherit'],
})
const lines = createInterface({ input: py.stdout })
const pending: ((v: any) => void)[] = []
lines.on('line', (l) => { const r = pending.shift(); if (r) r(JSON.parse(l)) })
py.on('exit', (c) => { if (c !== 0) { console.error(`kraken serve exited ${c}`); process.exit(1) } })

function askKraken(game: string, seed: number, view: unknown): Promise<any> {
  return new Promise((res) => {
    pending.push(res)
    py.stdin.write(JSON.stringify({ game, seed, view }) + '\n')
  })
}

interface Tally {
  kWins: number; tWins: number; ties: number; voids: number
  kBooks: number; tBooks: number; illegal: number; capped: number
  moves: number; errors: number; games: number
}
const zero = (): Tally => ({ kWins: 0, tWins: 0, ties: 0, voids: 0, kBooks: 0, tBooks: 0,
  illegal: 0, capped: 0, moves: 0, errors: 0, games: 0 })

// PER-GAME ROWS, because a point estimate with no interval is below this
// project's bar and because the bootstrap has to resample the unit that is
// independent. Games here are independent by construction -- a fresh seed and
// a fresh deal each -- so the game is the unit, and both sides of the seat
// swap are kept in one list so the pooled figure is what gets resampled.
const rows: { side: 0 | 1; i: number; kScore: number; tScore: number; voids: number; moves: number }[] = []

async function runSide(krakenTeam: 0 | 1, t: Tally): Promise<void> {
  const pairing = krakenTeam === 0 ? `kraken-vs-${THEIRS}` : `${THEIRS}-vs-kraken`
  for (let i = 0; i < N; i++) {
    const seed = `sim-${pairing}-${i}`
    let state: GameState = newGame(seed, undefined, (i % 6) as Seat)
    let steps = 0
    while (state.phase !== 'finished' && steps < 5000) {
      const seatIsKraken = (state.turn % 2) === krakenTeam
      const sd = hashSeed(`${seed}:${state.moveIndex}`)()
      let action
      if (seatIsKraken) {
        const rep = await askKraken(seed, sd, seatView(state, state.turn))
        if (rep.error) { t.errors++; console.error('KRAKEN ERROR', rep.error, rep.trace ?? ''); return }
        action = rep.action
      } else {
        action = decide(seatView(state, state.turn), THEIRS, sd)
      }
      const r = reduce(state, action)
      if (!r.ok) {
        t.illegal++
        console.error(`ILLEGAL from ${seatIsKraken ? 'KRAKEN' : 'theirs'}:`,
          r.error.code, r.error.message, JSON.stringify(action))
        return
      }
      state = r.state; steps++
    }
    t.moves += steps; t.games++
    if (state.phase !== 'finished') { t.capped++; continue }
    for (const bk of ALL_BOOKS) if (state.books[bk]?.outcome === 'void') t.voids++
    const kScore = state.score[krakenTeam], tScore = state.score[1 - krakenTeam]
    let vd = 0
    for (const bk of ALL_BOOKS) if (state.books[bk]?.outcome === 'void') vd++
    rows.push({ side: krakenTeam, i, kScore, tScore, voids: vd, moves: steps })
    t.kBooks += kScore; t.tBooks += tScore
    if (kScore > tScore) t.kWins++
    else if (tScore > kScore) t.tWins++
    else t.ties++
  }
}

const t = zero()
await runSide(0, t)
await runSide(1, t)
py.stdin.end()
const decided = t.kWins + t.tWins
console.log(JSON.stringify({
  spec: SPEC, theirs: THEIRS, gamesPerSide: N, games: t.games,
  krakenWins: t.kWins, theirWins: t.tWins, ties: t.ties,
  krakenWinPctOfDecided: decided ? +(100 * t.kWins / decided).toFixed(2) : null,
  booksPerGameKraken: +(t.kBooks / t.games).toFixed(3),
  booksPerGameTheirs: +(t.tBooks / t.games).toFixed(3),
  marginPerGame: +((t.kBooks - t.tBooks) / t.games).toFixed(3),
  voidsPerGame: +(t.voids / t.games).toFixed(3),
  avgMoves: +(t.moves / t.games).toFixed(1),
  illegal: t.illegal, capped: t.capped, errors: t.errors,
}))
if (process.env.ROWS) {
  const fs = await import('node:fs')
  fs.writeFileSync(process.env.ROWS, JSON.stringify({
    spec: SPEC, theirs: THEIRS, gamesPerSide: N, rows,
    illegal: t.illegal, capped: t.capped, errors: t.errors,
  }))
  console.error(`wrote ${rows.length} per-game rows to ${process.env.ROWS}`)
}
