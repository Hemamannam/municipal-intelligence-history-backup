# Data profile: NYC PLUTO tax lots

- Generated: 2026-08-10T11:38:42+00:00 (from local raw layer, latest record versions)
- Rows (distinct records): **858,602** — raw versions stored: 858,602
- Columns: **11**
- Configured primary key: `bbl`

## Primary-key candidates (unique + never null in sample)

- `bbl`

## Potential data-quality issues

- 1,499 rows (0.2%) missing coordinates

## Address inconsistencies (entity-resolution fuel)

- `address` mixes suffix spellings for STREET: ST (880), STREET (405,064)
- `address` mixes suffix spellings for AVENUE: AV (3), AVE (1,803), AVENUE (289,040)
- `address` mixes suffix spellings for BOULEVARD: BLVD (5,885), BOULEVARD (17,179)
- `address` mixes suffix spellings for ROAD: RD (215), ROAD (38,798)
- `address` mixes suffix spellings for PLACE: PL (14), PLACE (32,010)
- `address` mixes suffix spellings for COURT: COURT (9,687), CT (1)
- `address` mixes suffix spellings for PARKWAY: PARKWAY (6,506), PKWY (509)

## Categorical columns (top values)

- `borough`: QN (324,559), BK (276,311), SI (125,692), BX (89,496), MN (42,544)

## Column statistics

| column | null % | distinct | top values |
|---|---:|---:|---|
| `bbl` | 0.0 | 858,602 | 1000100019.00000000 (1); 1000120001.00000000 (1); 1000160125.00000000 (1) |
| `address` | 0.1 | 828,567 | HYLAN BOULEVARD (167); ARTHUR KILL ROAD (155); AMBOY ROAD (152) |
| `borough` | 0.0 | 5 | QN (324,559); BK (276,311); SI (125,692) |
| `zipcode` | 0.2 | 218 | 10314 (21,077); 10312 (19,567); 11234 (19,382) |
| `unitsres` | 0.1 | 768 | 1 (322,313); 2 (272,663); 0 (90,301) |
| `unitstotal` | 0.0 | 806 | 1 (343,606); 2 (268,578); 3 (92,366) |
| `ownername` | 0.1 | 730,218 | UNAVAILABLE OWNER (7,644); NYC DEPARTMENT OF PARKS AND RECREATION (5,010); NYC DEPARTMENT OF CITYWIDE ADMINISTRATIVE SERVICES (1,949) |
| `yearbuilt` | 0.0 | 253 | 1920 (87,239); 1930 (74,620); 1925 (69,439) |
| `bldgclass` | 0.0 | 221 | A1 (122,849); A5 (104,546); B1 (85,847) |
| `latitude` | 0.2 | 739,213 | 40.7371382 (9); 40.7383213 (7); 40.7385683 (6) |
| `longitude` | 0.2 | 765,389 | -74.0000180 (13); -73.9999784 (12); -73.9999567 (9) |
