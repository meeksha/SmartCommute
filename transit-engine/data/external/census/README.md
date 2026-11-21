# BBMP ward population (Census 2011)

`bbmp_wards_2011_population.csv`: the 198 BBMP wards (2010-2020 delimitation) with their Census 2011 population and
area, from Wikipedia "List of wards in Bangalore (2009-2023)". The total is 8,437,379, against an official BBMP
Census 2011 population of 8,443,675.

Ward location (`lat`, `lon`, `location_source`):
* 169 wards: a representative point of the KGIS ward boundary with the same name (datameet/Municipal_Spatial_Data,
  `Bangalore/BBMP.geojson`, 243-ward delimitation).
* 19 wards: the centre of BMTC GTFS stops named after the ward locality, taken only when they lie within 5 km of the
  neighbouring wards, which rules out same-named villages elsewhere.
* 10 wards (4.5 % of population): no named boundary or stop was found, so each is placed at the centre of its
  neighbouring wards (by ward number) and marked `interpolated`.

Used by the Digital Twin's statistical population, together with Census 2011 Table B-28 (Bangalore Urban, Urban),
the mode-by-distance distribution of 'other workers'.
