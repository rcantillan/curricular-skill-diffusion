# Field-residual community comparison and next temporal design

```bash
bash src/12_relational_comparison/run_comparison.sh
```

This runs a NEW analysis, communities_residual1, compares it with the already
completed communities1 and exports an audited field-specific hiring-rank proxy.
It preserves existing results. Optional arguments are residual tag, raw tag and
comparison tag, in that order. Changing a completed residual configuration or
its source code requires a new tag.

## Residual communities

The same initial program cohort and all 2,070 activities are retained. Before
constructing cosine similarities, each program's initial activity profile is
centered against the mean of other programs in the same field. Fields with fewer
than three initial nodes and zero residual profiles have no defined similarity
edges; they remain audited nodes but are excluded from community comparisons.
No subsequent changes or status values enter the partition. Scaling remains
the original skill-specific initial SD, rather than within-field variance.

This checks whether institutional deviations from field profiles reveal a
structure beyond the dominant disciplinary patterns. It does not guarantee that
measurement noise or disciplinary differences disappear. Main labels are arbitrary
integers and must not be matched across runs by their numeric values.

Residual outputs: outputs/relational_communities/communities_residual1.
Comparison outputs: outputs/relational_comparison/comparison1:

- network_structure_comparison.csv: disciplinary sorting, edge composition, support.
- paired_program_membership.csv: membership joined on institution × field.
- adjusted_change_tests.csv: descriptive adjusted tests for each network.
- community_changes.csv: raw group means and institution bootstrap intervals.
- paired_alignment_comparison.csv: residual versus raw alignment on common
  observed program-years; this is not a causal effect or a forecast test.

Sensitivity partitions vary resolution and neighbor count, but changes are still
summarized only for the main partition. The field-majority assignment accuracy is
a within-sample descriptive measure; reductions do not prove a superior model.
Comparisons may differ because residual zero/low-support nodes are excluded.

## Temporal diffusion: estimate relationships first, partition second

The similarity graph is a benchmark. A future temporal graph should represent
source-leading predictive relationships, not just similar content or coincident
changes. Proposed receiver unit: institution × field × activity × year.

1. Outcome: continuous activity-score increase or signed change, plus retention
   requiring subsequent observations. Keep binary adoption out until presence
   is validated. Do not duplicate the receiver outcome across candidate sources.
2. Source signal: an observed source increase from t-2 to t-1, preceding receiver
   change from t-1 to t. Own previous changes, collection coverage and common
   activity/field trends belong in the baseline.
3. Aggregate source signals at the receiver level, considering internal other
   fields, external same field and external different fields separately. Record
   source counts, missingness and observation support. Keep sources absent from
   collection distinct from sources with zero activity signal.
4. For external same-field sources, G = status(receiver)-status(source), oriented
   so negative G is a source above the receiver. Continuous signed and absolute
   gaps distinguish direction and proximity. Source-signal moments over gap
   functions (G, abs(G), directional functions or prespecified spline bases) can
   estimate gradients without arbitrary high/medium/low status bins. Overlapping
   moment regressors must be checked for algebraic collinearity under field-year
   effects and source-count normalization.
5. Discover these predictive weights only in an earlier period, compare against
   field-matched and temporally shifted sources, and validate incremental gains
   in later years against own-history/common-trend/zero-change baselines.
6. Build a directed graph from stable validated predictive weights, then estimate
   its communities and evaluate later change/consolidation. Record negative and
   unsupported edges; do not force them into a positive diffusion network.

This describes a NEXT model, not an analysis executed by run_comparison.sh.
Precedence plus incremental prediction still does not identify imitation:
common demand, organizational reforms and measurement processes may explain it.
Pairwise candidate screening needs multiple-testing and sample-splitting controls.

## Status support

The runner exports outputs/relational_comparison/status2015/status_2015_by_field.csv
using existing exact/explicit-alias matches for Computer Science, Business and
History. Higher values mean higher position (negative hiring rank standardized
within the full published field network). This is a continuous operational proxy,
not a proven cardinal measure of status. Apply only to those fields and outcomes
from 2014 onward. Do not average different fields into a university-wide score or
assign History status to another program. With only 2014–2017 outcomes, discovering
and validating an elaborate network will have limited temporal support.

Broader coverage requires an independently defensible earlier institution-level
measure. The 2022 networks are retrospective relative to the curricular window,
so they cannot become the primary prospective hierarchy without stating that
limitation. Carnegie remains categorical; no continuous distances are inferred
from its labels. The 161-category layer remains optional pending the real data.
