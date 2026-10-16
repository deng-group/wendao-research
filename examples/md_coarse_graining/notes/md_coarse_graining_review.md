# Literature review: MD coarse-graining and acceleration for ion transport in solid-state electrolytes

Written in the five-level form of [the graph schema](../../../docs/GRAPH_SCHEMA.md): method families,
techniques, papers, claims, quantities. `graph.json` in this workspace is this document as a graph; ids in
brackets are its node ids.

## The question

> Can we learn an efficient representation or dynamics model from atomistic simulations (MLIP-MD, AIMD) that
> predicts Li-ion transport accurately at larger spatial and temporal scales?

"Accurately" means the transport and mechanistic quantities: diffusivity, ionic conductivity, hop rates,
migration pathways, correlated migration. The question has three separable aims: spatial coarse-graining
(fewer degrees of freedom), temporal acceleration (fewer steps per unit of physical time), and dynamical
coarse-graining (learn hops, state transitions and rates instead of atomic motion). The distinction that
matters most across all of them: whether a method only samples structures faster, or preserves the true
dynamics. The first is comparatively easy; the second is what transport prediction needs.

## Level 1: method families

Each family is defined by what it keeps or learns, what it discards, and what it still has to compute.
Relevance is the reviewer's judgement against the question above (1 to 5), not a result from the literature.

| Family | Keeps / learns | Discards | Still computes | Relevance |
|---|---|---|---|---|
| **A. Fast MD / learned integrator** [family:a] | Full atomistic description; symplecticity and time reversibility of the dynamics | The intermediate integration steps | MD, with far fewer steps | 4 |
| **B. Spatial coarse-graining** [family:b] | A reduced set of degrees of freedom and an effective potential, optionally memory and noise | The eliminated atoms' explicit motion | MD in CG space | 3 |
| **C. Enhanced sampling** [family:c] | All atoms | The natural visiting order of states (a bias is added) | Biased MD; rates must be recovered | 5 |
| **D. Accelerated dynamics** [family:d] | Correct state-to-state dynamics of activated processes | The waiting time in metastable basins | MD with an acceleration strategy | 5 |
| **E. Kinetic coarse-graining** [family:e] | Discrete states and the transition probabilities or rates between them | Continuous motion within a state | MD only to build the model | 5 |
| **F. Generative dynamics / neural simulators** [family:f] | A learned distribution over future states or displacements, or a latent dynamics with a decoder | Step-by-step integration | MD only for training data | 5 |
| **G. Adaptive / multiscale simulation** [family:g] | Full resolution where and when it matters | Resolution elsewhere | Atomistic MD in part of the system or time | 4 |

Stated contrasts between families: A and F both learn long-interval atomic motion, but A keeps the geometric
structure of the integrator while F learns the transition distribution directly. C and D both accelerate
rare events, but the conditions under which true time and dynamics are recovered differ. B and E both
coarse-grain, but B compresses atoms and E compresses the state space. E and F both replace step-by-step MD,
but E has explicit states, transitions and rates while F learns distributions.

## Level 2: techniques

| Family | Technique | One line |
|---|---|---|
| A | Action learning [technique:action-learning] | Learn the action of a long interval so the induced map is symplectic and time-reversible |
| B | Force matching [technique:force-matching] | Fit a CG potential to projected atomistic forces; gives the CG free-energy surface |
| B | Coarse-graining auto-encoder [technique:cg-autoencoder] | Encoder = CG mapping, trained with a CG force field and a decoder |
| B | GNN CG potential [technique:gnn-cg-potential] | A graph neural network over beads as the transferable CG interaction |
| B | Generalized Langevin / Mori-Zwanzig memory [technique:generalized-langevin-memory] | CG dynamics with memory kernel, dissipation and noise from the eliminated degrees of freedom |
| B | Denoising force matching [technique:denoising-force-matching] | Force matching plus a denoising objective; far less data |
| C | Metadynamics [technique:metadynamics] | History-dependent bias along collective variables |
| C | Infrequent metadynamics [technique:infrequent-metadynamics] | Rare bias deposition; rescale escape times to recover unbiased rates |
| C | SPIB [technique:spib] | Reaction coordinate as the information bottleneck predicting the future state |
| C | Weighted ensemble [technique:weighted-ensemble] | Split and merge unbiased trajectories with weights; rates from weight flux |
| D | Hyperdynamics [technique:hyperdynamics] | Bias that raises basins and vanishes at dividing surfaces; clock advanced by the boost |
| D | Parallel replica dynamics [technique:parallel-replica-dynamics] | Independent replicas; first escape is the next event |
| D | Temperature-accelerated dynamics [technique:temperature-accelerated-dynamics] | Escapes at high T, filtered to the low-T sequence by harmonic TST |
| E | Markov state model [technique:markov-state-model] | Discrete states and P(s_{t+tau} given s_t) |
| E | VAMP [technique:vamp] | Variational score to train deep state decompositions (VAMPnets) |
| E | Kinetic Monte Carlo [technique:kinetic-monte-carlo] | Stochastic transitions from an event catalog with rates |
| E | k-ART [technique:k-art] | Off-lattice self-learning kMC; events found from local environments |
| E | Landmark analysis [technique:landmark-analysis] | Sites and hops from a trajectory without a predefined lattice |
| F | Flow matching [technique:flow-matching] | Velocity field transporting a prior to the conditional displacement distribution |
| F | Latent-space propagator [technique:latent-space-propagator] | Encode to slow variables, propagate there, decode |
| F | Descriptor-space prediction [technique:descriptor-trajectory-prediction] | Predict descriptor statistics as a time series, with uncertainty |
| F | Boltzmann generator [technique:boltzmann-generator] | Normalizing flow sampling P(R) directly; equilibrium, not dynamics |
| G | Adaptive resolution (AdResS) [technique:adaptive-resolution] | Molecules change resolution by region |

Techniques not yet backed by a paper in this review (OPES, umbrella sampling, transition path theory) are
not in the graph; they enter when a paper that uses them does.

## Level 3: papers

For every paper: what it learns, what it discards, and the validation levels it reports evidence for
(structural, thermodynamic, kinetic, transport, mechanistic). The validation levels were assigned from the
review's reading of each paper; verify against the paper before relying on them.

### A. Fast MD / learned integrator

**Bigi et al., PRL 2026, Learning the Action for Long-Time-Step Simulations of MD** [paper:bigi2026-learning-the-action], [doi:10.1103/shj2-hyw8](https://doi.org/10.1103/shj2-hyw8). Reading priority 3.
Learns a long-time-step map of positions and velocities through a learned action that enforces symplecticity
and time reversibility. Discards nothing in the degrees of freedom; skips the intermediate steps. Validated:
structural, thermodynamic (conservation, equipartition). Trains from short trajectories and transfers across
temperatures and compositions. Open: whether long-time diffusion statistics are preserved (see claim below).

### B. Spatial coarse-graining

**Wang & Gomez-Bombarelli, npj Comput. Mater. 2019, Coarse-graining auto-encoders** [paper:wang2019-cg-autoencoders], [doi:10.1038/s41524-019-0261-5](https://doi.org/10.1038/s41524-019-0261-5). Priority 4.
Learns the CG mapping, the CG force field and a decoder jointly. Discards the eliminated atoms; the CG
dynamics are not matched to atomistic time scales. Validated: structural, thermodynamic.

**Wang et al., ACS Cent. Sci. 2019, CGnet** [paper:wang2019-cgnet], [doi:10.1021/acscentsci.8b00913](https://doi.org/10.1021/acscentsci.8b00913).
Learns a CG free-energy function by force matching. Discards eliminated atoms, memory and friction.
Validated: thermodynamic, structural.

**Husic et al., J. Chem. Phys. 2020, Coarse graining MD with graph neural networks** [paper:husic2020-cg-gnn], [doi:10.1063/5.0026133](https://doi.org/10.1063/5.0026133).
A transferable CG interaction model as a GNN. Validated: thermodynamic, structural. (Cited in the original
review as Olsson et al. 2020, PMC7671749.)

**Lyu & Lei, PRL 2023, CG MD with many-body non-Markovian memory** [paper:lyu2023-cg-memory], [doi:10.1103/PhysRevLett.131.177301](https://doi.org/10.1103/PhysRevLett.131.177301). Priority 5.
Learns a many-body memory kernel in addition to the effective potential; the eliminated degrees of freedom
are kept as memory and noise. Validated: transport, kinetic (diffusivity, collective transport). Extends
CGnet by adding memory. The reason to doubt that a Li-only CG potential can predict diffusion kinetics.

**Durumeric et al., Nat. Commun. 2026, Force matching with denoising** [paper:durumeric2026-force-matching-denoising], [doi:10.1038/s41467-026-70818-0](https://doi.org/10.1038/s41467-026-70818-0).
Force matching plus denoising; far fewer atomistic samples. Validated: thermodynamic.

### C. Enhanced sampling

**Tiwary & Parrinello, PRL 2013, From metadynamics to dynamics** [paper:tiwary2013-metadynamics-kinetics], [doi:10.1103/PhysRevLett.111.230602](https://doi.org/10.1103/PhysRevLett.111.230602).
Unbiased transition rates from infrequent metadynamics, under the condition that transition states stay
unbiased. Validated: kinetic (hop rate).

**Wang & Tiwary, J. Chem. Phys. 2021, SPIB** [paper:wang2021-spib], [doi:10.1063/5.0038198](https://doi.org/10.1063/5.0038198).
A reaction coordinate from time-lagged information, including from under-sampled trajectories. Validated:
kinetic.

**Mehdi et al., JCTC 2022, SPIB-guided metadynamics** [paper:mehdi2022-spib-metadynamics], [doi:10.1021/acs.jctc.2c00058](https://doi.org/10.1021/acs.jctc.2c00058).
SPIB coordinates used to bias metadynamics, iterated. Validated: thermodynamic, kinetic. Extends SPIB.

**Zuckerman & Chong, Annu. Rev. Biophys. 2017, Weighted ensemble review** [paper:zuckerman2017-weighted-ensemble], [doi:10.1146/annurev-biophys-070816-033834](https://doi.org/10.1146/annurev-biophys-070816-033834).
Weight-splitting schemes that sample rare events without biasing the dynamics; rates from weight flux.
Validated: kinetic.

### D. Accelerated dynamics

**Voter, PRL 1997, Hyperdynamics** [paper:voter1997-hyperdynamics], [doi:10.1103/PhysRevLett.78.3908](https://doi.org/10.1103/PhysRevLett.78.3908).
A bias vanishing on dividing surfaces accelerates escapes with a known boost; discards the waiting time in
basins. Validated: kinetic.

**Voter, Montalenti & Germann, Annu. Rev. Mater. Res. 2002, Extending the time scale** [paper:voter2002-accelerated-md-review], [doi:10.1146/annurev.matsci.32.112601.141541](https://doi.org/10.1146/annurev.matsci.32.112601.141541).
Review of hyperdynamics, parallel replica, temperature-accelerated dynamics and on-the-fly kMC. The
reference and baseline against which learned accelerators are judged. Validated: kinetic.

### E. Kinetic coarse-graining

**Mardt et al., Nat. Commun. 2018, VAMPnets** [paper:mardt2018-vampnets], [doi:10.1038/s41467-017-02388-1](https://doi.org/10.1038/s41467-017-02388-1).
State decomposition and transition matrix end to end by maximising the VAMP score; discards motion within
states. Validated: kinetic (transition probabilities).

**Kahle, Musaelian, Marzari & Kozinsky, 2019, Unsupervised landmark analysis for jump detection** [paper:kahle2019-landmark-analysis], [arXiv:1902.02107](https://arxiv.org/abs/1902.02107) (Physical Review Materials, 2019; add the journal DOI).
Sites and hop events from ionic MD trajectories without a predefined lattice. Validated: kinetic,
mechanistic (residence times, hop events). Already read. Analysis, not prediction (claim below).

**El-Mellouhi, Mousseau & Lewis, PRB 2008, k-ART** [paper:elmellouhi2008-kart], [doi:10.1103/PhysRevB.78.153202](https://doi.org/10.1103/PhysRevB.78.153202).
Off-lattice self-learning kMC: events and barriers discovered from local environments, so local distortion
and off-lattice motion are handled without a predefined event list. Validated: kinetic, mechanistic.

### F. Generative dynamics / neural simulators

**Nam, Peng & Gomez-Bombarelli, Nat. Mach. Intell. 2025, LiFlow** [paper:nam2025-liflow], [doi:10.1038/s42256-025-01125-4](https://doi.org/10.1038/s42256-025-01125-4), [code](https://github.com/learningmatter-mit/liflow). Priority 1.
Learns P(dR | R_t, T), the distribution of atomic displacements over a time interval given structure and
temperature, by flow matching; a Propagator generates displacements, a Corrector repairs unphysical
structures. Discards step-by-step integration; still needs MD trajectories to train. Trained on 25 ps MD of
4,186 solid-electrolyte candidates at several temperatures; Li MSD on unseen compositions, Spearman about
0.7 to 0.8; speed-up up to about 600,000x relative to AIMD. Validated: transport (MSD), structural. The
paper closest to the question.

**Sidky, Chen & Ferguson, Chem. Sci. 2020, Molecular latent space simulators** [paper:sidky2020-latent-space-simulators], [doi:10.1039/D0SC03635H](https://doi.org/10.1039/D0SC03635H). Priority 2.
Encoder to slow latent variables, stochastic propagator there, decoder back to atoms; long trajectories of
protein models at far lower cost than MD. Validated: kinetic, structural. Contrasts with LiFlow: explicit
slow-variable dynamics versus a direct displacement distribution.

**Swinburne, PRL 2023, Compression and prediction of materials simulation trajectories with atomic descriptors** [paper:swinburne2023-descriptor-trajectories], [doi:10.1103/PhysRevLett.131.236101](https://doi.org/10.1103/PhysRevLett.131.236101).
A compressed descriptor-space state and its time series, with uncertainty; positions are not propagated.
Validated: structural.

**Noe, Olsson, Kohler & Wu, Science 2019, Boltzmann generators** [paper:noe2019-boltzmann-generators], [doi:10.1126/science.aaw1147](https://doi.org/10.1126/science.aaw1147).
A normalizing flow to the Boltzmann distribution; equilibrium structures and free energies without MD.
Discards time altogether. Validated: thermodynamic, structural. Contrasts with LiFlow: P(R) versus
P(dR | R_t, T).

### G. Adaptive / multiscale simulation

**Praprotnik, Delle Site & Kremer, J. Chem. Phys. 2005, AdResS** [paper:praprotnik2005-adress], [doi:10.1063/1.2132286](https://doi.org/10.1063/1.2132286).
Molecules switch between atomistic and CG representations by region with momentum-conserving coupling.
Validated: structural, thermodynamic. The event-driven analogue for electrolytes is a proposal (claim below).

## Level 4: claims

Status: `supported` or `contradicted` by papers in the graph, `contested`, `hypothesis` (the reviewer's
judgement, no direct evidence yet), `open` (an unanswered question).

| Claim | Status | Evidence | About |
|---|---|---|---|
| A CG potential that reproduces the equilibrium distribution does not determine the time scales of the CG dynamics [claim:cg-potential-does-not-fix-time-scales] | supported | Lyu & Lei 2023; Wang & Gomez-Bombarelli 2019 | force matching, GLE memory, family B |
| Coarse-graining away the host lattice leaves its effect on the mobile ions, to be represented as friction, noise or memory [claim:host-lattice-effects-persist] | hypothesis | (inference from Mori-Zwanzig) | family B |
| The CG mapping can be learned jointly with the CG potential [claim:learned-cg-mapping] | supported | Wang & Gomez-Bombarelli 2019 | CG auto-encoder |
| Sampling more transition events does not by itself give correct rates [claim:more-transitions-not-rates] | supported | Tiwary & Parrinello 2013; Zuckerman & Chong 2017 | family C, hop rate |
| Waiting time in basins dominates, so skipping it gives large speed-ups while keeping state-to-state dynamics [claim:waiting-time-dominates] | supported | Voter 1997; Voter et al. 2002 | family D, hyperdynamics |
| A symplectic, time-reversible long-step map need not reproduce long-time diffusion statistics [claim:symplecticity-not-sufficient-for-diffusion] | hypothesis | | action learning, diffusivity |
| A model of P(R) does not predict P(R_{t+tau} given R_t); equilibrium generators cannot give diffusion coefficients [claim:equilibrium-sampling-is-not-dynamics] | hypothesis | | Boltzmann generator, diffusivity |
| Agreement in MSD does not establish correct mechanisms, rates or correlated motion [claim:msd-agreement-insufficient] | open | | flow matching, MSD, migration pathway |
| LiFlow's 600,000x is relative to AIMD, not GPU MLIP-MD [claim:liflow-speedup-is-relative-to-aimd] | supported | Nam et al. 2025 | flow matching |
| Effective dynamics cannot be learned from short MD alone when important pathways never appear [claim:short-md-insufficient] | open | | families F, C |
| Which degrees of freedom coarse-graining should eliminate for solid electrolytes is undetermined [claim:what-to-eliminate-is-undetermined] | open | | families B, E, F |
| Structural and MSD agreement can coexist with wrong pathways; validation must be layered by goal [claim:validation-must-be-layered] | hypothesis | | MSD, migration pathway, hop rate |
| Automatic site and hop detection is analysis, not a predictive kinetic model [claim:event-detection-is-not-prediction] | hypothesis | | landmark analysis |
| An event-driven multiscale scheme would suit solid electrolytes [claim:event-driven-multiscale-for-electrolytes] | hypothesis | | family G, AdResS |

## Level 5: quantities

Grouped by validation level. Each has an operational definition in the graph.

| Level | Quantity | Definition |
|---|---|---|
| structural | Radial distribution function [quantity:rdf] | Histogram of interatomic distances for a species pair, normalised by the ideal-gas expectation |
| structural | Site occupancy [quantity:site-occupancy] | Fraction of frames in which each site holds a mobile ion |
| thermodynamic | Free-energy difference [quantity:free-energy-difference] | -kT log of the population ratio between states or along a collective variable |
| kinetic | Residence time [quantity:residence-time] | Mean time between arrival at a site and the next hop away |
| kinetic | Hop rate [quantity:hop-rate] | Detected hops per mobile ion per unit time; the escape rate in rate theory |
| kinetic | Transition probability [quantity:transition-probability] | P(state j at t+tau given state i at t), counted from trajectories |
| transport | Mean squared displacement [quantity:msd] | Average over ions and time origins of the squared displacement at lag t |
| transport | Diffusivity [quantity:diffusivity] | lim MSD(t) / (2 d t) over the diffusive regime |
| transport | Correlation factor [quantity:correlation-factor] | Tracer diffusivity over the uncorrelated random-walk diffusivity with the same hop rate and length |
| transport | Ionic conductivity [quantity:ionic-conductivity] | From the charge diffusivity (Nernst-Einstein) or the Green-Kubo current autocorrelation |
| mechanistic | Migration pathway [quantity:migration-pathway] | The sequence of sites and the saddle region of a hop; cooperative when several ions move together |

Which papers validate which quantities is in the graph as `validates` edges. The pattern it shows: the
generative and CG papers stop at structural, thermodynamic or MSD; only the rare-event and kinetic-model
papers report hop rates or pathways. That gap is the content of the open claims above.

## Reading order

1. LiFlow (2025): how time evolution is learned directly; how diffusion is validated.
2. Molecular latent space simulators (2020): learning true kinetics in a low-dimensional space.
3. Learning the Action (2026): skipping steps while keeping the structure of the dynamics.
4. CG auto-encoders (2019): learning a CG representation.
5. CG MD with memory (2023): why an effective potential alone may not describe diffusion.

Keep Voter 2002 as the reference for classical accelerated dynamics, and Kahle 2019 and k-ART 2008 as
references for automatic event discovery. Three strategies cover the five papers: learn a faster integrator;
learn a reduced representation; learn an effective stochastic dynamics.

## Where this leaves the question

Known: learned integrators, latent dynamics, kinetic state models and generative propagators each give a
route to larger scales. Uncertain: how much they differ in preserving true diffusion dynamics, handling
correlated hopping, and extrapolating to unseen transitions; none of the reviewed generative papers reports
hop rates or pathways. Decision this affects: whether the next stage centres on atomistic trajectory
prediction or on learning coarse-grained stochastic dynamics of the ions directly. Next step: compare families
A, B, E and F on what each learns, what it discards, and why it accelerates, rather than adding papers.
