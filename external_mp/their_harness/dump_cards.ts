// Ground truth for the card map, taken from THEIR constants rather than my reading of them.
import { ALL_BOOKS, ALL_CARDS, bookCards, cardBook } from '../lib/engine/index.ts'
const books = ALL_BOOKS.map((b, i) => ({ i, book: b, cards: bookCards(b) }))
const cards = ALL_CARDS.map((c) => ({ card: c, book: cardBook(c), bookIndex: ALL_BOOKS.indexOf(cardBook(c)) }))
console.log(JSON.stringify({ books, cards }, null, 0))
