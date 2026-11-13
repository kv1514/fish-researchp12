// The same shim, kept ALIVE across a whole game, purely as an instrument.
//
// WHY THIS EXISTS. `shim_decide.cpp` is stateless by design: a fresh process
// per decision, replaying the whole public log, which is what our website
// needs and what every published cross-engine number here was measured
// through. Their arbiter does not work that way. It constructs one agent per
// seat at the start of a deal and feeds it events as they happen.
//
// Those two are the same thing ONLY IF their agent is a pure function of
// (reset state, event sequence). Two ways it might not be, both introduced by
// their v0.4 and leaned on harder by every version after it:
//
//   * their belief is an iterative Sinkhorn/IPF fit, and an iterative fit that
//     warm-starts from the previous position converges somewhere a
//     from-scratch fit does not;
//   * their test-time search is determinized (det=12), drawing from the
//     agent's RNG. A fresh process re-seeds that stream at every decision, so
//     through our bridge their search may draw THE SAME determinizations every
//     turn, where in their own arbiter the stream advances.
//
// Either would degrade their play through our bridge without degrading it at
// home, and would do so more for later versions -- which is the shape
// `results/ladder_shape_comparison.json` found and could not explain.
//
// THIS FILE IS AN INSTRUMENT AND NOT A REPLACEMENT. `shim_decide.cpp` is left
// byte-for-byte alone: it produced the published numbers, and a file being
// investigated for a defect is the last file to edit while investigating it.
//
// Protocol: identical to shim_decide.cpp, except that after answering a DECIDE
// it FLUSHES and keeps reading instead of exiting. One process therefore plays
// a whole game, seeing each event once, in order, exactly as their arbiter's
// agent does. `QUIT` ends it.
#include "fish.hpp"
#include "game.hpp"
#include "factory.hpp"
#include <iostream>
#include <sstream>
#include <string>

using namespace fish;

int main() {
    std::ios::sync_with_stdio(false);
    std::string line, spec;
    Rules rules;
    int seat = 0;
    uint64_t hand = 0, seed = 1;
    PublicState pub;
    std::unique_ptr<Agent> agent;
    bool booted = false;
    auto boot = [&]() {
        if (booted) return;
        agent = makeAgent(spec);
        if (!agent) { std::cerr << "bad spec\n"; std::exit(2); }
        agent->reset(seat, hand, rules, seed);
        pub.rules = rules;
        for (int s = 0; s < NSET; s++) pub.setActive[s] = (s < rules.deckSets);
        pub.score[0] = pub.score[1] = 0;
        for (int p = 0; p < NPLAY; p++) pub.handCount[p] = uint8_t(rules.deckSets);
        booted = true;
    };
    while (std::getline(std::cin, line)) {
        std::istringstream in(line);
        std::string tag; in >> tag;
        if (tag == "QUIT") return 0;
        if (tag == "SPEC") { std::getline(in, spec); while (!spec.empty() && spec[0]==' ') spec.erase(0,1); }
        else if (tag == "RULES") { int oot, cl; in >> rules.deckSets >> oot >> cl;
            rules.outOfTurnDeclare = oot; rules.cardlessMayDeclare = cl; }
        else if (tag == "SEAT") in >> seat;
        else if (tag == "HAND") in >> hand;
        else if (tag == "SEED") in >> seed;
        else if (tag == "EV") {
            boot();
            std::string kind; in >> kind;
            Event e{};
            if (kind == "ASK") {
                int a,t,c,s; in >> a >> t >> c >> s;
                e.kind = Kind::Ask; e.actor=uint8_t(a); e.target=uint8_t(t);
                e.card=uint8_t(c); e.set=uint8_t(setOf(c)); e.success=s;
                for (int p = 0; p < NPLAY; p++) { int h; in >> h; e.handCount[p]=uint8_t(h); }
                pub.nAsks++;
            } else if (kind == "DECL") {
                int a,st,s; in >> a >> st >> s;
                e.kind = Kind::Declare; e.actor=uint8_t(a); e.set=uint8_t(st); e.success=s;
                e.decl.set = uint8_t(st);
                for (int i = 0; i < SETSZ; i++) { int o; in >> o; e.decl.owner[i]=uint8_t(o); }
                for (int p = 0; p < NPLAY; p++) { int h; in >> h; e.handCount[p]=uint8_t(h); }
                int s0, s1; in >> s0 >> s1;
                pub.setActive[st] = false; pub.score[0]=uint8_t(s0); pub.score[1]=uint8_t(s1);
            } else if (kind == "PASS") {
                int a,t; in >> a >> t;
                e.kind = Kind::Pass; e.actor=uint8_t(a); e.target=uint8_t(t);
                for (int p = 0; p < NPLAY; p++) { int h; in >> h; e.handCount[p]=uint8_t(h); }
            } else { std::cerr << "bad ev\n"; return 2; }
            for (int p = 0; p < NPLAY; p++) pub.handCount[p] = e.handCount[p];
            pub.nEvents++;
            pub.history.push_back(e);
            agent->observe(e);
        }
        else if (tag == "TURN") { boot(); in >> pub.turn; }
        else if (tag == "DECIDE") {
            boot();
            std::string what; in >> what;
            if (what == "TURN") {
                Declaration d; double conf = 0;
                if (agent->proposeDeclaration(pub, d, conf) && pub.setActive[d.set]) {
                    std::cout << "DECL " << int(d.set);
                    for (int i = 0; i < SETSZ; i++) std::cout << ' ' << int(d.owner[i]);
                    std::cout << std::endl; continue;
                }
                AskMove m = agent->chooseAsk(pub);
                if (isRepoll(m)) { std::cerr << "repoll from engine policy\n"; return 3; }
                std::cout << "ASK " << int(m.target) << ' ' << int(m.card)
                          << std::endl; continue;
            }
            if (what == "PASSTO") {
                int n; in >> n; int cand[NPLAY];
                for (int i = 0; i < n && i < NPLAY; i++) in >> cand[i];
                int t = agent->choosePassTarget(pub, cand, n);
                std::cout << "PASS " << t << std::endl; continue;
            }
            if (what == "FORCED") {
                int st; in >> st;
                Declaration d; double conf = 0;
                d.set = uint8_t(st);
                Declaration p2; double c2 = 0;
                if (agent->proposeDeclaration(pub, p2, c2) && p2.set == st) d = p2;
                else agent->bestGuess(pub, st, d, conf);
                std::cout << "DECL " << int(d.set);
                for (int i = 0; i < SETSZ; i++) std::cout << ' ' << int(d.owner[i]);
                std::cout << std::endl; continue;
            }
            std::cerr << "bad decide\n"; return 2;
        }
    }
    return 0;
}
