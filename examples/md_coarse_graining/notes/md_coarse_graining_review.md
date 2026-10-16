# Literature review: molecular dynamics coarse-graining and acceleration

**Scope: from classical accelerated MD, through machine-learning-based coarse-graining, to generative dynamics models that replace MD altogether.**

Rather than restricting the review to coarse-grained molecular dynamics in the traditional sense, it addresses a broader question:

> **Can we learn an efficient representation or dynamics model from atomistic simulations, enabling accurate predictions at larger spatial and temporal scales?**

The question contains three distinct goals, which can be pursued separately or combined:

1. **Spatial coarse-graining**: reduce the number of simulated degrees of freedom, e.g. represent several atoms as one particle, or keep only the occupancy state of mobile ions.
2. **Temporal acceleration**: reduce the number of computational steps needed per unit of physical time, e.g. predict the state 1 ps ahead directly instead of integrating 1 fs steps.
3. **Dynamical coarse-graining**: stop tracking the full atomic motion and learn ion hops, state transitions or other higher-level dynamical rules instead.

## 1. Proposed classification

Seven method families.

| Family | Core idea | Representative methods | Still runs MD? | Relevance to solid-state batteries |
|---|---|---|---|---|
| **A. Fast MD / learned integrator** | Larger time steps while preserving the true dynamics as far as possible | Symplectic ML, action learning | Yes, with fewer steps | 4/5 |
| **B. Spatial coarse-graining** | Fewer degrees of freedom; learn an effective potential and dynamics | CGnet, CG-VAE, force matching | Yes, in CG space | 3/5 |
| **C. Enhanced sampling** | Accelerate rare events; reach hard-to-sample states | Metadynamics, OPES, umbrella sampling | Yes, usually with a bias | 5/5 |
| **D. Accelerated dynamics** | Skip the long, uneventful waiting times | Hyperdynamics, TAD, parallel replica | Yes, with an acceleration strategy | 5/5 |
| **E. Kinetic coarse-graining** | Turn continuous trajectories into states and transitions | MSM, kMC, TPT | Not necessarily | 5/5 |
| **F. Generative dynamics / neural simulator** | Learn the distribution of future states or state transitions directly | Flow matching, diffusion, latent dynamics | Not at inference | 5/5 |
| **G. Adaptive / multiscale simulation** | Allocate compute by region, time or event importance | Adaptive resolution, concurrent multiscale, active learning | In some regions or stages | 4/5 |

The relevance scores are the reviewer's subjective judgement against the researcher's problem (ion transport in solid-state electrolytes), not quantitative conclusions from the literature.

The families overlap:

- A and F both learn atomic motion over long time intervals, but A emphasises the physical structure of the integrator.
- C and D both accelerate rare events, but the conditions under which true time and dynamics can be recovered differ.
- B and E are both coarse-graining, but B compresses atomic degrees of freedom while E compresses the state space.
- E and F both replace step-by-step atomistic simulation, but E has explicit states, transitions and rates, whereas F learns continuous or discrete probability distributions directly.

**The distinction that matters most is whether a method merely samples structures faster, or preserves the true dynamics.** Obtaining stable structures or equilibrium distributions is comparatively easy; predicting diffusivity, ionic conductivity, hop rates or correlated migration is much more demanding.

## 2. The three starting papers

### Paper 1: Learning the Action for Long-Time-Step Simulations of Molecular Dynamics

**Bigi et al., Physical Review Letters, 2026.** [doi:10.1103/shj2-hyw8](https://doi.org/10.1103/shj2-hyw8). Family A.

Conventional MD integrates Newton's equations one step at a time, (R_t, V_t) → (R_{t+Δt}, V_{t+Δt}). This paper learns a dynamical map over a long time interval directly and uses a learned mechanical action to guarantee important physical structure, including symplecticity and time reversibility. The authors argue this avoids the energy conservation and equipartition problems of ordinary ML trajectory predictors. The model learns from short trajectories and transfers across temperatures and chemical compositions.

It is not coarse-graining: no degrees of freedom are removed. The question it addresses is whether intermediate MD steps can be skipped without destroying the physical structure of the dynamics. For MLIP-based atomistic work this is an attractive route: keep the atomistic description, reduce the number of steps. Whether it preserves long-time diffusion statistics is the point to check; symplecticity does not automatically imply correct diffusivities or rare-event rates.

### Paper 2: Coarse-graining auto-encoders for molecular dynamics

**Wang & Gómez-Bombarelli, npj Computational Materials, 2019.** [doi:10.1038/s41524-019-0261-5](https://doi.org/10.1038/s41524-019-0261-5). Family B.

Closest to the traditional CG definition, in three steps: all-atom R → (encoder) CG variables z → (CG dynamics) z' → (decoder) R'. A VAE learns the coarse-grained representation, the corresponding effective force field, and the reconstruction of atomistic configurations. The key contribution is combining CG mapping, CG potential and reconstruction in one machine-learning framework; the valuable idea is that the mapping itself need not be specified by hand.

Open issue: a CG potential that describes the equilibrium distribution correctly does not give the CG dynamics the correct time scales, which matters for ionic diffusion.

### Paper 3: Flow matching for accelerated simulation of atomic transport in crystalline materials

**Nam et al., Nature Machine Intelligence, 2025.** [doi:10.1038/s42256-025-01125-4](https://doi.org/10.1038/s42256-025-01125-4) | [GitHub](https://github.com/learningmatter-mit/liflow). Family F.

From Rafael Gómez-Bombarelli's group; first author Juno Nam (Jiayu Peng, a co-author, worked in the same group). The method, **LiFlow**, does not generate each step by MD integration; it learns P(ΔR | R_t, T), the distribution of atomic displacements over a time interval given the current structure and temperature, with flow matching. A Propagator generates the displacements and a Corrector repairs unphysical structures.

Reported in the paper: training data from 4,186 candidate solid electrolytes; 25 ps MD trajectories at several temperatures; Spearman correlation of about 0.7 to 0.8 for Li MSD on unseen compositions; up to about 600,000× speed-up relative to first-principles simulation. The last number is relative to AIMD, not to GPU-accelerated MLIP-MD.

This is the closest to the researcher's work. It still needs MD training data, but once trained no MD integration is required. The question to pursue: can a generative model reproduce not only MSD but also the correct ion migration mechanisms, transition rates and correlated motions? That matters more than raw speed.

## 3. Representative literature by family

### A. Fast MD / learned integrator

| Paper | Contribution |
|---|---|
| [Bigi et al., PRL (2026)](https://doi.org/10.1103/shj2-hyw8) | Learned action; long-time-step integration that preserves geometric structure |

Keeps the atomistic description, needs no predefined migration sites. How to take large time steps when fast lattice vibrations are strongly coupled to slow ion migration remains to be studied.

### B. Spatial coarse-graining / ML coarse-grained force fields

| Paper | Contribution |
|---|---|
| [Wang & Gómez-Bombarelli, npj Comput. Mater. (2019)](https://doi.org/10.1038/s41524-019-0261-5) | VAE learns the CG mapping and the effective potential |
| [Wang et al., ACS Central Science (2019)](https://doi.org/10.1021/acscentsci.8b00913) | CGnet: CG free-energy function learned by force matching |
| [Husic et al., J. Chem. Phys. (2020)](https://pmc.ncbi.nlm.nih.gov/articles/PMC7671749/) | Graph neural networks for coarse-grained interactions |
| [Lyu & Lei, PRL (2023)](https://doi.org/10.1103/PhysRevLett.131.177301) | Many-body memory improves the description of collective transport and diffusion |
| [Durumeric et al., Nature Communications (2026)](https://doi.org/10.1038/s41467-026-70818-0) | Force matching combined with denoising; much lower data requirement for CG models |

Lyu & Lei (2023) deserves attention. Traditional coarse-graining tends to ignore the effect of eliminated degrees of freedom on the dynamics. In the Mori–Zwanzig framework, CG dynamics are governed not only by an effective potential but may also contain dissipation, random forces and memory effects; the paper shows many-body memory is important for predicting collective transport and diffusion correctly.

For solid electrolytes: if most of the host-lattice vibrations are coarse-grained away and only Li ions are kept, the influence of the host lattice on Li does not disappear. It may need to be represented through effective interactions, friction, noise or memory. Treating all Li as CG particles and training a simple CG potential is therefore unlikely to predict diffusion kinetics correctly.

### C. Enhanced sampling / ML collective variables

| Paper | Contribution |
|---|---|
| [Tiwary & Parrinello, PRL (2013)](https://doi.org/10.1103/PhysRevLett.111.230602) | Recovering transition kinetics from metadynamics |
| [Wang & Tiwary, J. Chem. Phys. (2021)](https://doi.org/10.1063/5.0038198) | SPIB: reaction coordinates learned from dynamical information |
| [Mehdi et al., JCTC (2022)](https://doi.org/10.1021/acs.jctc.2c00058) | SPIB-learned CVs guide metadynamics |
| [Weighted ensemble review (2017)](https://doi.org/10.1146/annurev-biophys-070816-033834) | Parallel trajectories with weight redistribution for efficient rare-event sampling |

The relevant line here is unsupervised or self-supervised CV learning: R(t) → (ML) s(t) → (bias) enhanced sampling, where s(t) is a low-dimensional collective variable learned from the trajectory. SPIB can learn a reaction coordinate from insufficiently sampled trajectories and use it for subsequent enhanced sampling.

Two things must be kept apart: **sampling more transition events ≠ having obtained correct transition rates.** For metadynamics, recovering real kinetics requires accounting for the effect of the bias on the dynamics and the applicability conditions of the corresponding methods.

### D. Accelerated dynamics / rare-event methods

| Paper | Contribution |
|---|---|
| [Voter, PRL (1997)](https://doi.org/10.1103/PhysRevLett.78.3908) | Hyperdynamics: raising the energy of metastable basins to accelerate rare transitions |
| [Voter et al., Annual Review of Materials Research (2002)](https://doi.org/10.1146/annurev.matsci.32.112601.141541) | Systematic review of hyperdynamics, parallel replica, temperature-accelerated dynamics and on-the-fly kMC |

These methods exploit a feature of materials dynamics: **the time a system waits in a metastable basin can be far longer than the time a transition takes.** Since most compute is spent waiting, the waiting can be skipped. The family is directly connected to activated diffusion in solids, has a much longer theoretical history than recent generative models, and provides physical constraints and baselines for ML methods.

### E. Kinetic coarse-graining / MSM / kMC

Rather than learning fewer atoms, convert continuous atomic motion into discrete states and transitions: R(t) → s(t) → P(s_{t+τ} | s_t).

| Paper | Contribution |
|---|---|
| [Mardt et al., Nature Communications (2018)](https://doi.org/10.1038/s41467-017-02388-1) | VAMPnets: kinetic models of MD built with deep learning |
| [Kahle et al., 2019](https://arxiv.org/abs/1902.02107) | Unsupervised landmark analysis: automatic identification of sites and hops from ionic MD trajectories |
| [El-Mellouhi et al., PRB (2008)](https://doi.org/10.1103/PhysRevB.78.153202) | k-ART: off-lattice self-learning kMC that discovers events and barriers automatically |

The landmark-analysis paper (already read) solves part of the problem of identifying sites and hops automatically from atomistic trajectories; it is trajectory analysis, not yet a model that predicts kinetics reliably in new environments. k-ART does not require a complete lattice event catalog: it finds transition events and barriers adaptively from the local environment, so dynamics can be modelled even with local structural distortion or off-lattice motion.

### F. Generative dynamics / neural simulators

| Paper | Contribution |
|---|---|
| [Sidky et al., Chemical Science (2020)](https://doi.org/10.1039/D0SC03635H) | Molecular latent space simulators: propagate dynamics in a slow-variable space and reconstruct atomistic configurations |
| [Swinburne, PRL (2023)](https://doi.org/10.1103/PhysRevLett.131.236101) | Compress and predict materials simulation trajectories with atomic descriptors |
| [Nam et al., Nature Machine Intelligence (2025)](https://doi.org/10.1038/s42256-025-01125-4) | LiFlow: flow matching generates atomic displacements in crystalline materials |

Molecular latent space simulators (LSS) follow R_t → (encoder) z_t → (propagator) z_{t+τ} → (decoder) R_{t+τ}: learn slow variables first, propagate in latent space, then regenerate atomistic configurations; demonstrated on protein models at far lower cost than MD. LiFlow instead learns the conditional distribution of atomic displacements directly, without an explicit low-dimensional slow-variable model. Both routes are worth following; they compress physical information differently. Swinburne (2023) offers a third approach: a compressed materials state built from atomic descriptors, time-series prediction in that space, and an estimate of prediction uncertainty.

### G. Adaptive / multiscale simulation

| Paper | Contribution |
|---|---|
| [Praprotnik et al., J. Chem. Phys. (2005)](https://doi.org/10.1063/1.2132286) | Adaptive resolution: dynamic switching between atomistic and CG representations |

Classical AdResS lets molecules change resolution according to the region they are in. For solid-state batteries a different design could be considered: a simplified dynamical description while an ion sits in a stable site, switching to an atomistic MLIP near a migration bottleneck or during a collective rearrangement. This is a possible extension, not something the AdResS paper has done for solid electrolytes.

## 4. A direction worth separating: direct generation of equilibrium configurations

**[Boltzmann generators, Noé et al., Science (2019)](https://doi.org/10.1126/science.aaw1147)** samples the equilibrium distribution directly with a generative model, giving equilibrium structures and thermodynamics without a long MD trajectory. But P(R) ≠ P(R_{t+τ} | R_t): the former is the equilibrium distribution, the latter describes dynamical transitions. A model that generates equilibrium structures perfectly need not predict a diffusion coefficient. Much current generative molecular simulation work targets equilibrium sampling rather than true time evolution.

## 5. What to focus on for solid-state battery research

| Research goal | Most relevant families | Main difficulty |
|---|---|---|
| Faster, accurate diffusion coefficients | A, D, E, F | Preserving true time scales and transition rates |
| Automatically learning migration mechanisms and pathways | C, E, F | Discovering unobserved states and transitions |
| Larger-scale ion transport, including disorder and collective migration | B, E, F, G | Keeping local-environment dependence and inter-ion dynamical correlation |

Three questions for later discussion:

**Question 1: what should coarse-graining eliminate?** Options for a solid electrolyte: remove high-frequency lattice vibrations but keep atomic coordinates; remove some framework atoms and keep mobile ions with an effective environment; remove in-site vibrations and keep only occupancy and migration events; keep no explicit atoms or sites and learn continuous latent dynamics. These lose entirely different information.

**Question 2: can effective dynamics be learned entirely from short MD trajectories?** If an important migration pathway never appears, the model may be unable to identify it. Enhanced sampling, active exploration or physical constraints may be needed, not just larger networks.

**Question 3: how to verify that coarse-grained dynamics are correct?** More important than the model architecture. Validation should be layered by goal:

| Level | What to check |
|---|---|
| Structural | RDF, site occupancy, local coordination |
| Thermodynamic | Free-energy differences, equilibrium populations |
| Kinetic | Residence time, transition probability, hop rate |
| Transport | MSD, diffusivity, correlation factor |
| Mechanistic | Migration pathways, cooperative hopping, environment-dependent jumps |

A model with the right structural distribution, even the right MSD, can still generate wrong migration pathways. Conversely, a model that cannot reconstruct instantaneous atomic positions but recovers transition kinetics correctly may be well suited to long-time transport simulation.

## 6. What to read next

Not all twenty papers at once. To understand how machine learning changes the time and length scales of MD, compare these five first:

| Priority | Paper | Focus |
|---|---|---|
| 1 | **LiFlow (2025)** | How to learn time evolution directly; how diffusion is validated |
| 2 | **Molecular latent space simulators (2020)** | How to learn true kinetics in a low-dimensional space |
| 3 | **Learning the Action (2026)** | How to skip time steps while keeping the structure of the dynamics |
| 4 | **Coarse-graining auto-encoders (2019)** | How to learn a coarse-grained representation automatically |
| 5 | **CG MD with memory (2023)** | Why learning an effective potential alone may not describe diffusion |

These cover three core strategies: learn a faster integrator; learn a reduced representation; learn an effective stochastic dynamics. Keep Voter (2002) as the reference for classical accelerated dynamics, and Kahle et al. (2019) and k-ART (2008) as references for automatic event discovery and kinetic modelling.

### Preliminary judgement

Coarse-graining does not have to mean merging atoms into particles; time, dynamical states, or the whole transition process can be coarse-grained. For ion diffusion in solid-state batteries the key may not be how many atoms are kept, but finding an effective representation that preserves the long-time dynamical rules.

- **What we know:** learned integrators, latent dynamics, kinetic state models and generative propagators already provide several acceleration routes.
- **What is uncertain:** how much the methods differ in preserving true diffusion dynamics, handling correlated hopping, and extrapolating to unseen transitions.
- **What decision this affects:** whether the next stage centres on atomistic trajectory prediction or on learning coarse-grained stochastic dynamics of the ions directly.
- **Best next step:** compare families A, B, E and F in depth, focusing not on more papers but on what each method learns, what it discards, and why it accelerates.
