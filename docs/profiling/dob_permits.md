# Data profile: NYC DOB NOW Approved Permits

- Generated: 2026-08-10T11:38:29+00:00 (from local raw layer, latest record versions)
- Rows (distinct records): **173,679** — raw versions stored: 173,679
- Columns: **42**
- Configured primary key: ``

## Primary-key candidates (unique + never null in sample)

- none found — a composite key is required

## Potential data-quality issues

- 25 fully duplicated rows (all columns identical)
- `applicant_middle_name` is 75% null/blank
- `expired_date`: 126,437 values in the future
- `filing_representative_middle_initial` is 96% null/blank
- `apt_condo_no_s` is 100% null/blank
- 807 rows (0.5%) missing coordinates

## Address inconsistencies (entity-resolution fuel)

- `street_name` mixes suffix spellings for STREET: ST (13), STREET (79,236)
- `street_name` mixes suffix spellings for AVENUE: AVE (16), AVENUE (59,992)
- `street_name` mixes suffix spellings for BOULEVARD: BLVD (3), BOULEVARD (5,913)
- `applicant_business_address` mixes suffix spellings for STREET: ST (3,944), STREET (35,907)
- `applicant_business_address` mixes suffix spellings for AVENUE: AV (47), AVE (12,302), AVENUE (28,488)
- `applicant_business_address` mixes suffix spellings for BOULEVARD: BLV (1), BLVD (8,102), BOULEVARD (1,903)
- `applicant_business_address` mixes suffix spellings for ROAD: RD (1,490), ROAD (7,495)
- `applicant_business_address` mixes suffix spellings for PLACE: PL (394), PLACE (5,106)
- `applicant_business_address` mixes suffix spellings for DRIVE: DR (358), DRIVE (2,744)
- `applicant_business_address` mixes suffix spellings for COURT: COURT (641), CT (444)
- `applicant_business_address` mixes suffix spellings for LANE: LANE (1,846), LN (304)
- `applicant_business_address` mixes suffix spellings for PARKWAY: PARKWAY (559), PKWY (149)

## Date ranges

| column | min | max | unparseable |
|---|---|---|---|
| `approved_date` | 2017-10-26 00:00:00 | 2026-08-07 00:00:00 | 0 |
| `issued_date` | 2025-08-01 00:00:00 | 2026-08-07 00:00:00 | 0 |
| `expired_date` | 2022-04-24 04:00:00 | 2027-08-07 00:00:00 | 0 |

## Categorical columns (top values)

- `sequence_number`: 1 (114,357), 2 (33,421), 3 (13,393), 4 (6,200), 5 (3,101), 6 (1,524)
- `filing_reason`: Initial Permit (113,259), Renewal Permit Without Changes (47,226), Renewal Permit with Changes (12,102), No Work Permit (775), None (317)
- `borough`: MANHATTAN (36,142), Manhattan (28,022), BROOKLYN (25,199), QUEENS (20,562), Brooklyn (19,887), Queens (14,910)
- `work_type`: General Construction (43,286), Plumbing (23,172), Mechanical Systems (17,008), Sidewalk Shed (14,317), Structural (13,463), Construction Fence (10,261)
- `permittee_s_license_type`: GC (128,427), P (24,356), F (11,008), R (4,878), S (2,748), PE (1,297)
- `applicant_middle_name`: J (6,995), A (5,649), M (4,406), S (3,579), C (3,362), R (2,586)
- `permit_status`: Permit Issued (131,904), Signed-off (41,775)
- `apt_condo_no_s`: OSP (12), N/A (2)

## Column statistics

| column | null % | distinct | top values |
|---|---:|---:|---|
| `job_filing_number` | 0.0 | 126,499 | Q00759854-I1 (45); Q01165922-I1 (40); B01056182-I1 (32) |
| `work_permit` | 0.0 | 131,350 | Q01104726-I1-GC-CX (20); Q00759854-I1-GC (15); S00739180-I1-GC-CX (15) |
| `sequence_number` | 0.0 | 18 | 1 (114,357); 2 (33,421); 3 (13,393) |
| `filing_reason` | 0.0 | 5 | Initial Permit (113,259); Renewal Permit Without Changes (47,226); Renewal Permit with Changes (12,102) |
| `house_no` | 0.0 | 12,630 | 1 (1,417); 200 (1,093); 60 (720) |
| `street_name` | 0.0 | 5,322 | BROADWAY (3,897); PARK AVENUE (2,610); 5 AVENUE (2,452) |
| `borough` | 0.0 | 10 | MANHATTAN (36,142); Manhattan (28,022); BROOKLYN (25,199) |
| `lot` | 0.0 | 719 | 1 (22,321); 7501 (7,733); 7502 (3,347) |
| `bin` | 0.0 | 45,088 | 1088961 (190); 1014387 (173); 1036205 (128) |
| `block` | 0.0 | 10,294 | 16 (500); 4905 (296); 1280 (273) |
| `c_b_no` | 0.5 | 69 | 105 (14,395); 108 (9,282); 102 (7,055) |
| `work_on_floor` | 4.0 | 14,113 | Open Space (26,489); Roof (9,684); Facade (7,783) |
| `work_type` | 0.0 | 21 | General Construction (43,286); Plumbing (23,172); Mechanical Systems (17,008) |
| `permittee_s_license_type` | 0.0 | 9 | GC (128,427); P (24,356); F (11,008) |
| `applicant_license` | 0.0 | 9,101 | 620254 (1,267); 613329 (1,228); 623618 (1,206) |
| `applicant_first_name` | 0.0 | 3,540 | MICHAEL (4,877); JOSEPH (3,998); JOHN (3,962) |
| `applicant_middle_name` | 75.2 | 30 | J (6,995); A (5,649); M (4,406) |
| `applicant_last_name` | 0.0 | 6,387 | SINGH (8,391); WU (1,766); KAUR (1,584) |
| `applicant_business_name` | 0.0 | 9,002 | PLATINUM SERVICES NY LLC (1,267); SUNRUN INSTALLATION SVC (1,228); STREAM ROCK CONTSRUCTION* (1,206) |
| `applicant_business_address` | 0.0 | 8,790 | 53-28 11TH STREET 2ND FL (1,267); 775 FIERO LN STE 200 (1,228); 963 FOREST HILL ROAD (1,206) |
| `approved_date` | 0.0 | 2,286 | 2025-11-12T00:00:00.000 (601); 2025-09-19T00:00:00.000 (581); 2025-08-11T00:00:00.000 (581) |
| `issued_date` | 0.0 | 331 | 2026-06-22T00:00:00.000 (1,055); 2026-06-30T00:00:00.000 (998); 2025-11-06T00:00:00.000 (980) |
| `expired_date` | 0.0 | 1,445 | 2026-12-31T00:00:00.000 (3,959); 2026-09-30T00:00:00.000 (2,608); 2026-12-31T05:00:00.000 (2,540) |
| `job_description` | 0.0 | 90,917 | INSTALLATION OF TEMPORARY HEAVY DUTY SIDEWALK SHED AS PER PL; PROPOSED INSTALLATION OF HEAVY DUTY SIDEWALK SHED AS PER PLA; INSTALLATION OF TEMPORARY SIDEWALK SHED AS PER PLANS. NO CHA |
| `estimated_job_costs` | 0.0 | 26,402 | 0 (22,555); 1000 (9,872); 5000 (7,503) |
| `owner_business_name` | 3.8 | 12,793 | PR (26,159); Not Applicable (19,488); NYCHA (4,210) |
| `owner_name` | 2.2 | 30,792 | CHARLESTON ALBERT (1,884); JOSEPH SCALISI (1,690); Chirag Patel (1,511) |
| `permit_status` | 0.0 | 2 | Permit Issued (131,904); Signed-off (41,775) |
| `tracking_number` | 0.0 | 147,436 | 474490529 (6); 763129662 (6); 483461947 (5) |
| `zip_code` | 0.0 | 220 | 10022 (3,753); 10019 (3,155); 10011 (2,963) |
| `latitude` | 0.5 | 40,617 | 40.753045 (190); 40.751614 (173); 40.762495 (131) |
| `longitude` | 0.5 | 40,271 | -74.000282 (190); -73.992121 (173); -73.974482 (129) |
| `community_board` | 0.5 | 67 | 105 (14,433); 108 (9,202); 102 (7,083) |
| `council_district` | 0.5 | 51 | 4 (16,828); 3 (11,552); 1 (8,504) |
| `bbl` | 3.9 | 40,661 | 3020410001 (210); 1007027501 (190); 1007830070 (173) |
| `census_tract` | 0.5 | 1,485 | 122 (1,066); 7 (1,066); 137 (1,060) |
| `nta` | 0.5 | 234 | Midtown-Times Square (8,797); Upper East Side-Carnegie Hill (5,562); Midtown South-Flatiron-Union Square (4,000) |
| `filing_representative_first_name` | 46.4 | 1,614 | ELY (2,710); ALDI (2,298); MOHAMMED (1,984) |
| `filing_representative_last_name` | 46.4 | 2,028 | SEPULVEDA (2,764); DILO (2,298); ISLAM (1,971) |
| `filing_representative_business_name` | 47.0 | 2,013 | AE DESIGN SOLUTION INC. (2,712); Rigid Structural Design, LLC (2,300); JENNY FLORES EXPEDITING (1,974) |
| `filing_representative_middle_initial` | 96.5 | 32 | M (939); J (807); V (751) |
| `apt_condo_no_s` | 100.0 | 2 | OSP (12); N/A (2) |
