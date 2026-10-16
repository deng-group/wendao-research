# Literature Review：Molecular Dynamics Coarse-Graining & Acceleration

**研究范围：从传统 accelerated MD 到 machine-learning-based coarse-graining，再到完全替代 MD 的生成式动力学模型。**

我建议这次不要把范围局限在传统意义上的 coarse-grained molecular dynamics，而是研究一个更大的问题：

> **Can we learn an efficient representation or dynamics model from atomistic simulations, enabling accurate predictions at larger spatial and temporal scales?**

这个问题实际上包含三个不同目标：

1. **Spatial coarse-graining**：减少需要模拟的自由度，例如把若干原子表示为一个粒子，或者只保留离子的占位状态。
2. **Temporal acceleration**：减少模拟相同物理时间所需的计算步骤，例如从 1 fs 直接预测 1 ps 后的状态。
3. **Dynamical coarse-graining**：不再追踪完整原子运动，而是学习离子跃迁、状态转移或更高层次的动力学规律。

它们可以独立存在，也可以相互结合。

## 1. 我建议采用的文献分类

初步将这个领域分为 **7 个主要方向**。

| 分类 | 核心思想 | 代表方法 | 是否需要继续做 MD | 与固态电池的相关性 |
|---|---|---|---|---|
| **A. Fast MD / Learned Integrator** | 增大时间步长，同时尽量保留真实动力学 | Symplectic ML, Action Learning | 是，但步数更少 | ⭐⭐⭐⭐ |
| **B. Spatial Coarse-Graining** | 减少自由度，学习有效势能和动力学 | CGnet, CG-VAE, Force Matching | 是，但在 CG 空间运行 | ⭐⭐⭐ |
| **C. Enhanced Sampling** | 加速稀有事件发生，探索难以到达的状态 | Metadynamics, OPES, Umbrella Sampling | 是，通常引入 bias | ⭐⭐⭐⭐⭐ |
| **D. Accelerated Dynamics** | 跳过大量无意义的等待时间 | Hyperdynamics, TAD, Parallel Replica | 是，但采用加速策略 | ⭐⭐⭐⭐⭐ |
| **E. Kinetic Coarse-Graining** | 把连续原子轨迹转换成状态及状态间的跃迁 | MSM, kMC, TPT | 不一定 | ⭐⭐⭐⭐⭐ |
| **F. Generative Dynamics / Neural Simulator** | 直接学习未来状态或状态转移分布 | Flow Matching, Diffusion, Latent Dynamics | 推理阶段可以不需要 | ⭐⭐⭐⭐⭐ |
| **G. Adaptive / Multiscale Simulation** | 根据空间、时间或事件重要性动态分配计算资源 | Adaptive Resolution, Concurrent Multiscale, Active Learning | 部分区域或阶段需要 | ⭐⭐⭐⭐ |

星级是我根据你研究的固态电池离子输运问题给出的**主观相关性评估**，不是文献中的量化结论。

这七类并非完全互斥，例如：

- A 和 F 都可能学习较长时间间隔的原子运动，但 A 更强调动力学积分的物理结构。
- C 和 D 都可以加速 rare events，但它们恢复真实时间和动力学的条件不同。
- B 和 E 都是 coarse-graining，但前者主要压缩原子自由度，后者压缩状态空间。
- E 和 F 都能替代逐步原子模拟，但 E 通常有显式状态、跃迁和速率，F 可以直接学习连续或离散的概率分布。

**我认为最值得关注的区别，是一个方法仅仅能更快地采样结构，还是能够正确保留真实动力学。**

如果目标只是获得稳定结构或者平衡分布，问题相对简单；如果目标是预测 diffusivity、ionic conductivity、hop rate 或 correlated migration，要求就高得多。

## 2. 先确认你提到的三篇文章

这三篇文章非常适合作为我们 review 的起点，因为它们代表了三个不同方向。

### Paper 1 — Learning the Action for Long-Time-Step Simulations of Molecular Dynamics

**Bigi et al., Physical Review Letters, 2026**

[论文链接](https://doi.org/10.1103/shj2-hyw8)

**分类：A. Learned Integrator**

核心思想：

传统 MD 通过积分 Newton's equations 得到下一步的位置：

\[
(\mathbf R_t,\mathbf V_t)
\longrightarrow
(\mathbf R_{t+\Delta t},\mathbf V_{t+\Delta t})
\]

这篇文章希望直接学习一个较长时间间隔的动力学映射，并利用机械作用量（action）来保证映射具有重要的物理结构，包括 symplecticity 和 time reversibility。

作者强调，这有助于避免普通 ML trajectory predictor 中的能量守恒和能量均分问题。模型可以从短轨迹学习，并在不同温度、化学组成条件下迁移。:chatgpt-content-reference{index="0"}

**值得关注的地方：**

它不是传统的 coarse-graining，因为没有减少原子自由度。

它真正尝试解决的是：

> Can we skip intermediate MD steps without destroying the physical structure of the dynamics?

对于你的研究，这提供了一种很有吸引力的路线：保留 MLIP 和 atomistic description，但减少计算步骤。

不过，我会特别注意它能否保留 long-time diffusion statistics。满足 symplecticity 并不自动意味着 diffusivity、rare-event rate 都正确。

---

### Paper 2 — Coarse-graining auto-encoders for molecular dynamics

**Wang & Gómez-Bombarelli, npj Computational Materials, 2019**

[论文链接](https://doi.org/10.1038/s41524-019-0261-5)

**分类：B. Spatial Coarse-Graining**

这是更符合传统 CG 定义的文章。

它包含三个步骤：

\[
\underbrace{\mathbf R}_{\text{All atoms}}
\xrightarrow{\text{Encoder}}
\underbrace{\mathbf z}_{\text{CG variables}}
\xrightarrow{\text{CG dynamics}}
\mathbf z'
\xrightarrow{\text{Decoder}}
\mathbf R'
\]

作者利用 VAE 学习 coarse-grained representation，同时学习相应的 effective force field，并能够重建 atomistic configurations。

关键贡献是将 CG mapping、CG potential 和 reconstruction 结合到一个机器学习框架中。:chatgpt-content-reference{index="1"}

我觉得这里最有价值的思想是：

**不一定要提前人工规定哪些原子应该组成一个 coarse-grained particle，mapping 本身也可以通过机器学习获得。**

但是还有一个重要问题：

学习一个能够正确描述 equilibrium distribution 的 CG potential，不代表 CG dynamics 自动具有正确的动力学时间尺度。

这一点在研究 ionic diffusion 时尤其重要。

---

### Paper 3 — Flow matching for accelerated simulation of atomic transport in crystalline materials

**Nam et al., Nature Machine Intelligence, 2025**

[论文链接](https://doi.org/10.1038/s42256-025-01125-4) | [GitHub](https://github.com/learningmatter-mit/liflow)

**分类：F. Generative Dynamics**

我觉得这很可能就是你记得的那篇 MIT 文章。

它来自 Rafael Gómez-Bombarelli 的团队，不过第一作者是 **Juno Nam**，而不是 Jiayu Peng。Jiayu Peng 确实曾在同一研究组工作，也与 Juno Nam 合作发表过其他 MLIP 论文。:chatgpt-content-reference{index="2"}

这篇文章提出了 **LiFlow**。

它的核心思想是：

不通过传统 MD 积分来生成每一步运动，而是直接学习：

\[
P(\Delta\mathbf R\mid\mathbf R_t,T)
\]

也就是给定当前结构和温度，预测下一段时间内原子位移的概率分布。

它采用 Flow Matching，并结合 Propagator 与 Corrector 来生成位移及修正不合理的结构。

论文中：

- 使用 4,186 种固态电解质候选材料的数据。
- 使用不同温度下的 25 ps MD 轨迹。
- 对未见组成的 Li MSD 预测，Spearman correlation 达到约 0.7–0.8。
- 报告了相对于 first-principles simulations 最高约 600,000 倍的加速。:chatgpt-content-reference{index="3"}

注意，最后这个数字是相对于 AIMD 的比较，并不意味着它相对于 GPU-accelerated MLIP-MD 也能加速同样的倍数。

**这篇和你的研究非常接近。**

不过它仍然需要 MD training data，只是在模型训练完成后，可以不再依赖传统 MD 积分生成轨迹。

因此真正需要研究的是：

> Can a generative model reproduce not only MSD, but also correct ion migration mechanisms, transition rates, and correlated motions?

我认为这是比单纯追求模拟速度更重要的问题。

---

## 3. 其他方向的代表性文献

下面列的是我认为值得纳入第一轮 review 的论文。主要按照方法学分类，而不是按照应用材料分类。

### A. Fast MD / Learned Integrator

这一类的主要目标是加大时间步长，而非减少原子数。

| Paper | 主要贡献 |
|---|---|
| [Bigi et al., PRL (2026)](https://doi.org/10.1103/shj2-hyw8) | Learning action，实现保持特定几何结构的长时间步动力学积分 |

这个方向可以先以 Bigi et al. 为入口。

它的优势是保留 atomistic description，不需要事先定义 migration sites。

但是，快速变化的晶格振动与慢速离子迁移高度耦合时，如何使用大时间步仍然值得研究。

### B. Spatial Coarse-Graining / ML Coarse-Grained Force Fields

这是最正统的 coarse-grained MD 路线。

| Paper | 主要贡献 |
|---|---|
| [Wang & Gómez-Bombarelli, npj Comput. Mater. (2019)](https://doi.org/10.1038/s41524-019-0261-5) | VAE 自动学习 CG mapping 和 effective potential |
| [Wang et al., ACS Central Science (2019)](https://doi.org/10.1021/acscentsci.8b00913) | CGnet：通过 force matching 学习 CG free-energy function |
| [Olsson et al., J. Chem. Phys. (2020)](https://pmc.ncbi.nlm.nih.gov/articles/PMC7671749/) | 利用 GNN 学习 coarse-grained interactions |
| [Lyu & Lei, PRL (2023)](https://doi.org/10.1103/PhysRevLett.131.177301) | 引入 many-body memory，改善 collective transport 和 diffusion 的动力学描述 |
| [Durumeric et al., Nature Communications (2026)](https://doi.org/10.1038/s41467-026-70818-0) | 结合 force matching 和 denoising，大幅降低 CG 模型的数据需求 |

其中，我认为 **Lyu & Lei (2023)** 特别值得注意。

传统 coarse-graining 容易忽略被消除自由度对动力学的影响。

在 Mori–Zwanzig framework 下，CG dynamics 一般不仅受到 effective potential 控制，还可能包含：

- Dissipation
- Random forces
- Memory effects

这篇文章强调，多体 memory 对 collective transport 和 diffusion 的正确预测非常重要。:chatgpt-content-reference{index="4"}

对于固态电解质，你可能会遇到一个问题：

假设我们把 host lattice 的大部分振动都 coarse-grain 掉，只保留 Li ions，那么 host lattice 对 Li 的影响并不会因此消失。

这些影响可能需要通过 effective interaction、friction、noise 或 memory 来表示。

这也是为什么我认为直接把所有 Li 当作 CG particles，再训练一个简单的 CG potential，未必足以正确预测 diffusion kinetics。

### C. Enhanced Sampling / ML Collective Variables

这一类的主要目标不是减少原子自由度，而是让系统更容易探索罕见状态。

| Paper | 主要贡献 |
|---|---|
| [Tiwary & Parrinello, PRL (2013)](https://doi.org/10.1103/PhysRevLett.111.230602) | 从 Metadynamics 中恢复 transition kinetics |
| [Wang & Tiwary, J. Chem. Phys. (2021)](https://doi.org/10.1063/5.0038198) | SPIB：利用动力学信息学习 reaction coordinates |
| [Mehdi et al., JCTC (2022)](https://doi.org/10.1021/acs.jctc.2c00058) | 利用 SPIB 学习的 CV 指导 Metadynamics，实现 enhanced sampling |
| [Weighted Ensemble review (2017)](https://doi.org/10.1146/annurev-biophys-070816-033834) | 通过并行轨迹及权重重分配更高效地采样 rare events |

这里最适合你关注的是 **unsupervised 或 self-supervised CV learning**。

例如：

\[
\mathbf R(t)
\xrightarrow{\text{ML}}
s(t)
\xrightarrow{\text{Bias}}
\text{Enhanced Sampling}
\]

其中 \(s(t)\) 是模型从轨迹中学习的低维 collective variable。

SPIB 的一个重要特点是可以从不充分采样的轨迹中学习 reaction coordinate，并用于后续 enhanced sampling。:chatgpt-content-reference{index="5"}

但必须区别两件事：

**采样到更多跃迁事件 ≠ 已经正确获得了跃迁速率。**

对于 Metadynamics，如果需要恢复真实 kinetics，必须考虑 bias 对动力学的影响以及相应方法的适用条件。:chatgpt-content-reference{index="6"}

### D. Accelerated Dynamics / Rare-Event Methods

这是一个比较成熟、但容易被 ML 文献 review 忽视的领域。

| Paper | 主要贡献 |
|---|---|
| [Voter, PRL (1997)](https://doi.org/10.1103/PhysRevLett.78.3908) | Hyperdynamics：通过抬高 metastable basins 的能量加速罕见跃迁 |
| [Voter et al., Annual Review of Materials Research (2002)](https://doi.org/10.1146/annurev.matsci.32.112601.141541) | 系统综述 Hyperdynamics、Parallel Replica、Temperature-Accelerated Dynamics 和 on-the-fly kMC |

这类方法利用了材料动力学的一个重要特点：

**系统在 metastable basin 中等待的时间可能远远长于实际发生 transition 的时间。**

既然大多数计算时间都花在等待上，就可以尝试跳过这些等待。

这一类与固体中的 activated diffusion 有非常直接的联系，而且其理论历史比近年来的生成式模型长得多。:chatgpt-content-reference{index="7"}

它也能给 ML 方法提供有价值的物理约束和 baseline。

### E. Kinetic Coarse-Graining / MSM / kMC

这类方法与传统 spatial coarse-graining 的区别尤其重要。

我们不一定需要学习更少的原子，而是把原子的连续运动转化为离散状态及状态之间的跃迁：

\[
\mathbf R(t)
\longrightarrow
s(t)
\longrightarrow
P(s_{t+\tau}\mid s_t)
\]

| Paper | 主要贡献 |
|---|---|
| [Mardt et al., Nature Communications (2018)](https://doi.org/10.1038/s41467-017-02388-1) | VAMPnets：通过深度学习构建分子动力学的 kinetic model |
| [Kahle et al., 2019](https://arxiv.org/abs/1902.02107) | Unsupervised landmark analysis：从离子 MD 轨迹中自动识别占位和跃迁 |
| [El-Mellouhi et al., PRB (2008)](https://doi.org/10.1103/PhysRevB.78.153202) | k-ART：off-lattice self-learning kMC，自动发现 events 和 barriers |

这里特别要提到你之前已经读过的 **Unsupervised landmark analysis for jump detection in molecular dynamics simulations**。

它已经解决了一部分从 atomistic trajectory 自动识别 site 和 hop 的问题。

不过，它主要解决的是 trajectory analysis，并不等于已经建立了能够在新环境下可靠预测 kinetics 的模型。:chatgpt-content-reference{index="8"}

另外，k-ART 很值得看看。

它并不要求预先定义完整的 lattice event catalog，而是根据局域环境自适应寻找跃迁事件和势垒。

因此即使材料存在局域结构畸变或 off-lattice motion，也可以进行动力学建模。:chatgpt-content-reference{index="9"}

### F. Generative Dynamics / Neural Simulators

这一类是近年来 ML 与 dynamics 结合的重要研究方向。

| Paper | 主要贡献 |
|---|---|
| [Sidky et al., Chemical Science (2020)](https://doi.org/10.1039/D0SC03635H) | Molecular Latent Space Simulators：在慢变量空间推进动力学并重建原子构型 |
| [Swinburne, PRL (2023)](https://doi.org/10.1103/PhysRevLett.131.236101) | 利用 atomic descriptors 压缩并预测材料模拟轨迹 |
| [Nam et al., Nature Machine Intelligence (2025)](https://doi.org/10.1038/s42256-025-01125-4) | LiFlow：基于 Flow Matching 生成晶体材料中的原子位移 |

我想特别强调 **Molecular Latent Space Simulators (2020)**。

它与 LiFlow 的区别很有意思。

LSS 的框架是：

\[
\mathbf R_t
\xrightarrow{\text{Encoder}}
\mathbf z_t
\xrightarrow{\text{Propagator}}
\mathbf z_{t+\tau}
\xrightarrow{\text{Decoder}}
\mathbf R_{t+\tau}
\]

它先学习 slow variables，再在 latent space 中推进动力学，最后重新生成 atomistic configurations。

作者在蛋白质模型上展示了能够以远低于传统 MD 的成本生成长时间轨迹。:chatgpt-content-reference{index="10"}

相比之下，LiFlow 直接学习原子位移的条件分布，没有要求先构造一个显式的低维 slow-variable dynamics model。

两条路线都值得关注，但它们对物理信息的压缩方式不同。

Swinburne (2023) 则提供了第三种思路：利用 atomic descriptors 建立压缩的材料状态表示，在这个空间中直接进行时间序列预测，并估计预测的不确定性。:chatgpt-content-reference{index="11"}

### G. Adaptive / Multiscale Simulation

这一类不是统一降低整个系统的分辨率，而是在不同区域或者不同阶段使用不同的计算模型。

| Paper | 主要贡献 |
|---|---|
| [Praprotnik et al., J. Chem. Phys. (2005)](https://doi.org/10.1063/1.2132286) | Adaptive Resolution：在 atomistic 与 CG representations 之间动态切换 |

传统 AdResS 允许分子根据所在区域在不同分辨率之间切换。:chatgpt-content-reference{index="12"}

对固态电池，可以进一步考虑一种不同的设计：

当离子处于稳定 site 时，使用简化动力学描述；当它接近 migration bottleneck 或发生 collective rearrangement 时，再切换到 atomistic MLIP。

这属于我认为可以研究的扩展方案，**并不是说上面的 AdResS 论文已经在固态电解质中实现了这种事件驱动机制**。

---

## 4. 还有一个值得单独区分的方向：直接生成 equilibrium configurations

这类方法也可能完全不需要逐步 MD，但它们与预测真实 dynamics 有本质区别。

代表论文：

**[Boltzmann Generators — Noé et al., Science (2019)](https://doi.org/10.1126/science.aaw1147)**

这篇文章通过生成模型直接采样 equilibrium distribution，从而获得平衡结构和热力学信息，而不需要通过漫长 MD 轨迹依次访问不同状态。:chatgpt-content-reference{index="13"}

但是：

\[
P(\mathbf R)
\neq
P(\mathbf R_{t+\tau}\mid\mathbf R_t)
\]

前者描述 equilibrium distribution；后者描述 dynamical transitions。

因此，即使一个模型能够完美生成平衡结构，也未必能预测扩散系数。

这一点非常重要，因为现在不少 generative molecular simulation 工作更关注 equilibrium sampling，而非真实时间演化。

---

## 5. 对你的固态电池研究，应该重点关注什么？

我们现在可以稍微把文献与研究问题联系起来，但不急着确定新的项目。

我认为可以用三个不同目标来筛选这些文献。

| 研究目标 | 最值得关注的方法 | 主要难点 |
|---|---|---|
| **更快地获得准确的 diffusion coefficient** | A、D、E、F | 能否保留真实时间尺度与跃迁速率 |
| **自动学习离子迁移机制和 migration pathways** | C、E、F | 如何发现未观测到的状态和跃迁 |
| **在更大尺度模拟离子输运，包括 disorder 和 collective migration** | B、E、F、G | 如何保留局域环境依赖性及离子间的动力学关联 |

这里我想提出三个值得后续专门讨论的研究问题。

**问题一：Coarse-graining 到底应该消除什么？**

对于固态电解质，存在多种可能的表示：

- 消除高频晶格振动，但仍然保留原子坐标。
- 消除部分 framework atoms，只保留移动离子与有效环境。
- 消除 site 内的振动，只保留 occupancy 和 migration events。
- 不再保留明确的原子或 site，而是学习连续 latent dynamics。

这几种方法损失的信息完全不同。

**问题二：能否完全从短 MD trajectory 中学习有效动力学？**

这是 ML 方向最吸引人的问题之一。

但仅利用短轨迹学习时，存在一个根本困难：如果某个重要的迁移路径从未出现过，模型可能无法识别它。

因此我们可能还需要结合 enhanced sampling、active exploration 或物理约束，而不只是训练更复杂的神经网络。

**问题三：如何检验 coarse-grained dynamics 是否正确？**

我认为这比模型结构本身更值得关注。

特别是在固态电解质中，验证指标应该根据研究目标分层：

| 层次 | 验证内容 |
|---|---|
| Structural | RDF、site occupancy、local coordination |
| Thermodynamic | Free-energy differences、equilibrium populations |
| Kinetic | Residence time、transition probability、hop rate |
| Transport | MSD、diffusivity、correlation factor |
| Mechanistic | Migration pathways、cooperative hopping、环境依赖的跃迁 |

一个模型即使结构分布正确，甚至 MSD 也接近参考结果，仍然可能生成错误的 migration pathways。

反过来，某些模型虽然无法准确重建每个原子的瞬时位置，但如果能正确恢复 transition kinetics，也可能非常适合长时间输运模拟。

---

## 6. 下一步应该读什么？

虽然上面列出了二十篇左右的文献，但我不建议现在逐篇阅读。

如果目的是了解 **machine learning 如何真正改变 MD 的时间和空间尺度**，我建议首先深入比较这五篇：

| 优先级 | Paper | 重点看什么 |
|---|---|---|
| 1 | **LiFlow (2025)** | 怎样直接学习时间演化？如何验证 diffusion？ |
| 2 | **Molecular Latent Space Simulators (2020)** | 怎样在低维空间中学习真实 kinetics？ |
| 3 | **Learning the Action (2026)** | 怎样跳过时间步，同时保留动力学结构？ |
| 4 | **Coarse-graining Auto-encoders (2019)** | 怎样自动学习 coarse-grained representation？ |
| 5 | **Construction of CG MD with Memory (2023)** | 为什么只学习 effective potential 可能不足以描述 diffusion？ |

这五篇基本覆盖三种核心策略：

\[
\boxed{
\begin{aligned}
&\text{Learn a faster integrator}\\
&\text{Learn a reduced representation}\\
&\text{Learn an effective stochastic dynamics}
\end{aligned}
}
\]

同时建议保留 Voter (2002) 作为传统 accelerated dynamics 的理论参照，以及 Kahle et al. (2019) 和 k-ART (2008) 作为自动事件发现与动力学建模的参照。

### 我的初步判断

我觉得这次文献整理最重要的收获是：

**Coarse-graining 不一定意味着把几个原子合并成一个粒子。我们也可以 coarse-grain 时间、动力学状态，甚至整个 transition process。**

而对于固态电池中的离子扩散，最关键的也许不是保留多少原子，而是找到一种能够保留长时间动力学规律的有效表示。

目前不需要急着选择一个具体算法。我们已经有足够的信息先确定研究范围。

**What we know →** 现有研究已经提供了 learned integrator、latent dynamics、kinetic state models、generative propagators 等多种加速路线。

**What is uncertain →** 不同方法在保留真实扩散动力学、处理 correlated hopping、外推到未见跃迁方面的能力差异有多大。

**What decision this affects →** 下一阶段应该以 atomistic trajectory prediction 为核心，还是直接学习离子的 coarse-grained stochastic dynamics。

**Best next step →** 我建议首先深入比较 **A、B、E、F 四类**，重点不是再增加论文数量，而是明确各方法究竟学习了什么、舍弃了什么，以及它们为什么能够加速模拟。
