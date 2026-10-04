# Data profile: NYC DCWP Legally Operating Businesses

- Generated: 2026-08-10T11:38:37+00:00 (from local raw layer, latest record versions)
- Rows (distinct records): **69,884** — raw versions stored: 69,884
- Columns: **30**
- Configured primary key: `license_nbr`

## Primary-key candidates (unique + never null in sample)

- `license_nbr`

## Potential data-quality issues

- `lic_expir_dd`: 44,304 values in the future
- `unit_type` is 85% null/blank
- `apt_suite` is 86% null/blank
- `detail` is 88% null/blank
- `dba_trade_name` is 86% null/blank
- `street3` is 100% null/blank
- 23,889 rows (34.2%) missing coordinates
- 747 rows with coordinates outside the NYC bounding box

## Address inconsistencies (entity-resolution fuel)

- `address_street_name` mixes suffix spellings for STREET: ST (12,110), STREET (4,423)
- `address_street_name` mixes suffix spellings for AVENUE: AVE (16,397), AVENUE (5,168)
- `address_street_name` mixes suffix spellings for BOULEVARD: BLVD (2,885), BOULEVARD (681)
- `address_street_name` mixes suffix spellings for ROAD: RD (2,947), ROAD (495)
- `address_street_name` mixes suffix spellings for PLACE: PL (707), PLACE (157)
- `address_street_name` mixes suffix spellings for DRIVE: DR (922), DRIVE (60)
- `address_street_name` mixes suffix spellings for COURT: COURT (13), CT (286)
- `address_street_name` mixes suffix spellings for LANE: LANE (49), LN (438)
- `address_street_name` mixes suffix spellings for PARKWAY: PARKWAY (118), PKWY (472)

## Date ranges

| column | min | max | unparseable |
|---|---|---|---|
| `license_creation_date` | 1900-12-31 00:00:00 | 2026-04-16 00:00:00 | 0 |
| `lic_expir_dd` | 2019-09-30 00:00:00 | 2100-12-18 00:00:00 | 0 |

## Categorical columns (top values)

- `license_type`: Premises (53,317), Individual (16,567)
- `license_status`: Active (43,581), Expired (18,642), Surrendered (2,711), Failed to Renew (1,918), Ready for Renewal (1,671), Revoked (556)
- `address_type`: Complete Address (52,290), Cross Street (Intersection) (880), Place (Landmark) (52), P.O. Box (15)
- `address_borough`: Queens (13,129), Brooklyn (13,067), Manhattan (9,986), Bronx (6,144), Outside NYC (3,786), Staten Island (2,998)
- `unit_type`: APT (3,971), STE (3,238), FL (1,377), UNIT (1,086), FRNT (280), RM (214)
- `street3`: MADISON AVENUE (3)

## Column statistics

| column | null % | distinct | top values |
|---|---:|---:|---|
| `license_nbr` | 0.0 | 69,884 | 0132715-DCA (1); 0225766-DCA (1); 0368322-DCA (1) |
| `business_name` | 0.0 | 58,302 | T-MOBILE NORTHEAST LLC (289); SP PLUS CORPORATION (280); ecoATM, LLC (129) |
| `business_unique_id` | 0.0 | 62,932 | BA-1305489-2022 (10); BA-1302088-2022 (7); BA-1458176-2022 (6) |
| `business_category` | 0.0 | 48 | Home Improvement Contractor (18,437); Tobacco Retail Dealer (6,586); Secondhand Dealer - General (5,415) |
| `license_type` | 0.0 | 2 | Premises (53,317); Individual (16,567) |
| `license_status` | 0.0 | 11 | Active (43,581); Expired (18,642); Surrendered (2,711) |
| `license_creation_date` | 0.0 | 7,342 | 1900-12-31T00:00:00.000 (164); 2018-02-23T00:00:00.000 (104); 2025-05-16T00:00:00.000 (103) |
| `lic_expir_dd` | 0.0 | 283 | 2027-02-28T00:00:00.000 (12,951); 2026-12-31T00:00:00.000 (6,044); 2027-07-31T00:00:00.000 (4,118) |
| `contact_phone` | 27.5 | 37,238 | 2123217542 (215); (425) 279-4550 (201); 8587667242 (190) |
| `address_type` | 23.8 | 4 | Complete Address (52,290); Cross Street (Intersection) (880); Place (Landmark) (52) |
| `address_street_name` | 23.8 | 10,148 | BROADWAY (1,307); JAMAICA AVE (474); 5TH AVE (414) |
| `address_city` | 0.0 | 2,097 | BROOKLYN (16,961); NEW YORK (12,424); BRONX (8,376) |
| `address_state` | 0.1 | 50 | NY (65,308); NJ (1,881); Outside USA (261) |
| `address_zip` | 0.0 | 3,431 | 11235 (952); 11214 (848); 11385 (843) |
| `address_borough` | 29.7 | 6 | Queens (13,129); Brooklyn (13,067); Manhattan (9,986) |
| `community_board` | 35.8 | 67 | 105 (2,198); 412 (1,441); 407 (1,410) |
| `council_district` | 35.9 | 51 | 04 (2,034); 03 (1,896); 01 (1,341) |
| `census_tract` | 35.9 | 1,295 | 96 (495); 21 (215); 76 (205) |
| `latitude` | 34.2 | 31,890 | 40.758226805707956 (32); 40.58230457095598 (32); 40.67004755675707 (26) |
| `longitude` | 34.2 | 31,896 | -73.96606610619004 (32); -74.16905343328875 (32); -73.84264537457251 (26) |
| `address_building` | 25.1 | 9,932 | 1 (237); 200 (167); 10 (165) |
| `unit_type` | 85.0 | 20 | APT (3,971); STE (3,238); FL (1,377) |
| `apt_suite` | 85.5 | 1,764 | 1 (1,192); 2 (857); 3 (319) |
| `bin` | 37.6 | 27,641 | 4000000 (213); 3000000 (141); 2000000 (84) |
| `bbl` | 37.6 | 27,566 | 4115440100 (47); 1010990043 (44); 4050447501 (35) |
| `nta` | 37.1 | 193 | MN17 (1,522); QN55 (701); MN13 (677) |
| `census_block_2010_` | 37.1 | 264 | 1000 (3,862); 2000 (3,465); 1001 (3,144) |
| `detail` | 88.4 | 852 | Vendor Type: General Vendor (White) (1,598); Vendor Type: Citywide Specialized Vendor (Yellow) (798); Product Category: Fruits, Vegetables, Flowers, Soft Drinks,  |
| `dba_trade_name` | 86.3 | 6,705 | T-Mobile 4110 (112); ecoATM (101); AT&T MOBILITY (90) |
| `street3` | 100.0 | 1 | MADISON AVENUE (3) |
