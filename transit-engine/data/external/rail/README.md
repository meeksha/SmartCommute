# Bengaluru <-> Tumakuru rail data (collected 19 Nov 2026)

Only trains marked **Daily** are included, so every train runs on any date the planner is asked about.

* `trains.csv`: stop times. The full MEMU stop lists come from etrain.info train schedule pages
  (66567, 66568, 66569, 66570, 66571, 66572, 66573, 66574). For passenger and express trains, only the
  boarding/alighting times at the Bengaluru station and at Tumakuru are included, taken from erail.in
  "trains between stations" (TK <-> SBC). Those trains also stop elsewhere, but their intermediate times
  were not collected, so the planner never boards or alights them there.
* `stations.csv`: station coordinates and the source of each one. Golhalli (GHL) and Muddalinganahalli (MDLL)
  halts are left out because no published coordinates were found; MEMUs still pass through them.
* Fares: unreserved second-class fare SBC -> TK is Rs 20 (etrain.info fare calculator, GN quota, 71 km).
  The Indian Railways minimum fare of Rs 10 applies to short MEMU hops (e.g. Malleswaram -> Chikkabanavara,
  Asianet News). Express fares vary by class and are not published per segment, so for those trains
  the ordinary Rs 20 fare is shown as a lower bound.
* Emissions: Indian Railways electric MEMU/passenger rail uses the same lifecycle per-passenger-km band as the
  Metro (grid-electric rail, ITF/World Bank India); express trains may be diesel- or electric-hauled, and this
  is reflected in a wider range.

Sources:
- https://etrain.info/train/Sbc-Tk-Memu-66567/schedule (and the other MEMU schedule pages)
- https://erail.in/trains-between-stations/tumkur-TK/ksr-bengaluru-SBC
- https://erail.in/trains-between-stations/ksr-bengaluru-SBC/tumkur-TK
- https://mapcarta.com/N853131485 (Tumakuru station, OSM node 853131485)
- Wikipedia station articles: Soldevanahalli, Nidvanda, Dobbspet, Hirehalli, Kyatsandra
