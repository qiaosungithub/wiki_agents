# 从 untied 深层网络到 weight sharing：Adam 与 Muon 的同一个更新问题

2026-09-10。按研究者要求重新建立 formulation：先在完整的 untied 非线性网络中得到 Adam / Muon 的最优更新，再引入 tying 等式。本文不依赖收缩系数或预先设定的 depth 幂律。

这里“最优”指给定当前梯度、optimizer state 和更新预算后的一步最优解。网络的 loss 保留其非线性和非凸性；没有把整个训练任务替换成二维二次函数。

主要结论：Muon 的标准谱范数预算在 untied 时得到逐层正交化，直接加入 tying 约束后得到对梯度和做正交化。完整 Adam 的逐调用二阶矩若作为既定度量保留下来，则同样的 tying 操作给出

\[
\boxed{\Delta_*=-\eta\Big(\sum_iD_i\Big)^{-1}\sum_i m_i},
\qquad D_i=\operatorname{diag}(\sqrt{\widehat v_i}+\epsilon).
\tag{1}
\]

它在每个坐标上是对各调用 Adam 更新的 RMS 加权平均；不是归一化后等权相加。这个权重来自原优化问题的等式约束，不需要指定调用距离。

## 1. 起点是完整的深层网络

设网络有 \(T\) 个 block，block 内可以包含 attention、MLP、非线性、归一化和残差。先将准备共享的参数展开为独立副本：

\[
\begin{aligned}
h_i&=f_i(h_{i-1};W_i),\\
\mathcal L(W_1,\ldots,W_T)
&=\mathbb E_{(x,y)}\ell(h_T,y).
\end{aligned}
\tag{2}
\]

取 \(G_i=\nabla_{W_i}\mathcal L\)。这些是完整网络反向传播得到的梯度，已经包含所有下游 block 的影响。对当前一步的任意小更新，只有一阶展开

\[
\mathcal L(W+\Delta W)
=\mathcal L(W)+\sum_i\langle G_i,\Delta W_i\rangle
+o(\|\Delta W\|).
\tag{3}
\]

Muon 博客处理的是如何选择这一小步的约束，而不是用某个 Hessian 代替整个网络。本文采用它的形式：

\[
\min_{\Delta W_1,\ldots,\Delta W_T}
\sum_i\langle G_i,\Delta W_i\rangle
\quad\text{s.t.}\quad
\mathcal N(\Delta W_1,\ldots,\Delta W_T)\leq\eta.
\tag{4}
\]

其中 \(\mathcal N\) 描述更新预算。它不是由 Hessian 唯一决定的；选择预算就是选择优化器的几何。若有适当的光滑性界，预算也可用于控制高阶余项；没有这样的界时，有限学习率的实际下降仍需检查。

参考：[Deriving Muon，第 1–3 步](https://jeremybernste.in/writing/deriving-muon)。这篇博客通过线性层的输入输出尺度来选择更新范数。以下 tying 推导是在明确的预算选择之上独立推得。

## 2. Untied 时，为什么逐层 Muon 是最优

考虑一个 block 内的线性映射 \(z_i=W_i x_i\)。暂时固定当前输入，参数更新对本层输出的直接影响是

\[
\delta z_i=\Delta W_i x_i,\qquad
\|\delta z_i\|_{\rm RMS}
\leq\|\Delta W_i\|_{{\rm RMS}\to{\rm RMS}}
\|x_i\|_{\rm RMS}.
\]

若各层输入已做适当尺度控制，一个自然的局部预算是限制每层算子增益。相同宽度时可写成

\[
\mathcal N(\Delta W)=\max_i\|\Delta W_i\|_{\rm op}.
\tag{5}
\]

这里 \(\|\cdot\|_{\rm op}\) 是谱范数。不同宽度时，RMS-to-RMS 范数还带 \(\sqrt{d_{\rm in}/d_{\rm out}}\) 的系数，可以保留在各层预算中。

式 (4) 现在等价于同时要求每个 \(\|\Delta W_i\|_{\rm op}\leq\eta\)。由于 untied 的更新变量相互独立，优化可按层分解。对 \(G_i=U_i\Sigma_iV_i^T\)，谱范数的对偶不等式给出

\[
\langle G_i,\Delta W_i\rangle
\geq-\eta\|G_i\|_{\rm nuc},
\]

取

\[
\boxed{\Delta W_i^*=-\eta\,\operatorname{polar}(G_i)
=-\eta U_iV_i^T}
\tag{6}
\]

即可达到下界。这就是理想化 Muon 的更新方向。

逐层“归一化”的原因由此明确：每层有自己的可行更新变量和算子预算。只要该层梯度非零，最优解会把它自己的预算用满。并不需要假设各层梯度范数接近，也不需要推测曲率与梯度成正比。

这里的 polar 取一个满足支持函数等式的解；满秩时是通常的极分解因子，秩亏时最优解可能不唯一。实际 Muon 用有限次 Newton–Schulz 近似该方向，并通常以 momentum 构造线性项，不能把近似实现和任意有限步训练的最优性等同起来。[Muon 实现说明](https://kellerjordan.github.io/posts/muon/)

所有层都能在一次更新中前进，来自式 (5) 的 max 聚合。若把预算换成各层范数之和，最优解可能只更新一层。逐层 normalization 因此也包含了跨层预算的选择。[Modular Duality，第 2、3 节](https://arxiv.org/html/2410.21265v1)

## 3. Untied 时，Adam 在什么意义下是最优

先按 [Old Optimizer, New Norm，Story I](https://arxiv.org/html/2409.20325v2) 的设定，关闭 EMA，并忽略数值稳定项。Adam 退化为逐元素 sign 更新。选择

\[
\mathcal N_\infty(\Delta W)
=\max_i\|\operatorname{vec}(\Delta W_i)\|_\infty
\]

作为式 (4) 的预算，便得到

\[
\boxed{\Delta W_i^*=-\eta\,\operatorname{sign}(G_i).}
\tag{7}
\]

这是 Adam 无 EMA 版本的精确对应。它控制的是每个元素的最大位移，与 Muon 的算子预算不同。

对于完整 Adam，固定当前 bias-corrected 的 \(m_i=\widehat m_i\) 与 \(D_i=\operatorname{diag}(\sqrt{\widehat v_i}+\epsilon)\succ0\)，把矩阵展开为向量 \(\delta_i\)。其一步更新是下面问题的精确解：

\[
\min_{\delta_1,\ldots,\delta_T}
\sum_i\left[m_i^T\delta_i+
\frac{1}{2\eta}\delta_i^TD_i\delta_i\right].
\tag{8}
\]

它等价于在相应椭球预算下最小化同一个线性项，并选取使拉格朗日乘子为 \(1/\eta\) 的预算大小。独立变量的一阶条件给出

\[
\boxed{\delta_i^*=-\eta D_i^{-1}m_i.}
\tag{9}
\]

二次项是指定的更新代价，不是声称网络 loss 为二次函数，也不是声称 \(D_i\) 等于 Hessian。以 \(m_i\) 替换当前梯度后，“最优”针对 momentum 线性项；它不自动保证当前 batch loss 下降。本文先不包括 weight decay、gradient clipping 和学习率调度。

平方根二阶矩也可以通过一个明确的度量选择问题来说明。把 untied 网络所有参数坐标合在一起，设历史梯度的原始二阶矩为 \(v_k\)。在对角度量的总预算 \(\sum_k d_k=C\) 下，最小化历史梯度的平均对偶能量：

\[
\min_{d_k>0,\,\sum_kd_k=C}
\mathbb E[g^TD^{-1}g]
=\min_{d_k>0,\,\sum_kd_k=C}\sum_k\frac{v_k}{d_k}.
\]

对于正的 \(v_k\)，拉格朗日条件 \(-v_k/d_k^2+\lambda=0\) 给出

\[
d_k=\frac{C\sqrt{v_k}}{\sum_j\sqrt{v_j}}
\propto\sqrt{v_k}.
\]

这个比例因子对全网络所有坐标相同，可以并入 learning rate；再代入式 (8)，就得到完整 Adam 的预条件形式。EMA 可作为这里历史样本的指数权重，epsilon 则作为避免退化的正则化。这没有推出 EMA 的具体时间尺度或 trace 预算是唯一正确的选择；它明确了在什么统计预算下平方根二阶矩最优，避免把它直接叫作 Hessian。

至此，untied 情形已经先得到了需要的两个 optimizer，而没有借助任何 depth 衰减公式。

## 4. 自然的 tying：同一个网络，只限制参数子空间

共享网络就是

\[
\mathcal L_{\rm tied}(\Theta)
=\mathcal L(\Theta,\ldots,\Theta).
\tag{10}
\]

为了比较同一个前向函数，在展开模型的 \(W_1=\cdots=W_T=\Theta\) 处取梯度。继续保持 sharing，要求每次更新满足

\[
\Delta W_1=\cdots=\Delta W_T=\Delta\Theta.
\tag{11}
\]

这是一条线性等式约束。原来有 \(T\) 个更新变量，现在只能选择一个。把式 (11) 直接代入式 (4)：

\[
\boxed{
\min_{\Delta\Theta}
\Big\langle\sum_iG_i,\Delta\Theta\Big\rangle
\quad\text{s.t.}\quad
\mathcal N(\Delta\Theta,\ldots,\Delta\Theta)\leq\eta.}
\tag{12}
\]

对谱范数 max 预算，约束化简为 \(\|\Delta\Theta\|_{\rm op}\leq\eta\)，所以

\[
\boxed{\Delta\Theta_*=-\eta\,
\operatorname{polar}\Big(\sum_iG_i\Big).}
\tag{13}
\]

对元素 max 预算，同理得到

\[
\boxed{\Delta\Theta_*=-\eta\,
\operatorname{sign}\Big(\sum_iG_i\Big).}
\tag{14}
\]

这是逐层 Muon / sign-Adam 到共享版本的直接过渡。梯度始终来自同一个深层 loss，预算也没有在 tying 时换掉。

若原预算为 \(\max_i a_i\|\Delta W_i\|_{\rm op}\leq\eta\)，tying 后只是 \((\max_i a_i)\|\Delta\Theta\|_{\rm op}\leq\eta\)。因此，仅仅给 early 调用更紧的标量预算，在这种几何下只会改变共享更新的整体步长，并不会产生 \(\operatorname{polar}(\sum_i w_iG_i)\) 中的不同梯度系数。

对于部分 sharing，可以按共享组重复这个推导：同组梯度先求和，不同组仍各自解自己的约束问题。更一般的线性参数化 \(W=P\Theta\) 则给出梯度 \(P^TG\) 和诱导范数 \(\mathcal N(P\Delta\Theta)\)。这里完全不要求网络浅、线性或收缩。

## 5. 一个不依赖 depth 的量：sharing 损失了多少一步自由度

在相同谱范数预算下，untied 的最优一阶下降量是

\[
B_{\rm untied}=\eta\sum_i\|G_i\|_{\rm nuc},
\]

而 tied 的最优一阶下降量是

\[
B_{\rm tied}=\eta\Big\|\sum_iG_i\Big\|_{\rm nuc}.
\]

因此，若分母非零，

\[
\boxed{\chi=
\frac{\|\sum_iG_i\|_{\rm nuc}}
{\sum_i\|G_i\|_{\rm nuc}}\in[0,1].}
\tag{15}
\]

这个比值精确衡量在当前一阶问题中，tying 保留了多少最优下降能力。若各调用梯度为同一矩阵的正倍数，则 \(\chi=1\)。若不同调用强烈抵消，则 \(\chi\) 可能很小。对于 sign-Adam，把 nuclear norm 换成逐元素 \(\ell_1\) 范数即可。

这是约束子空间造成的损失，不是训练收敛率的保证。它给出了一个不需要引入统一 Jacobian 收缩系数的分析对象：共享调用之间对更新方向的兼容程度。

## 6. 保留完整 Adam 的度量再 tying，会得到另一种共享更新

现在对式 (8) 加同一条 \(\delta_i=\delta\) 约束，得到

\[
\min_\delta
\Big(\sum_i m_i\Big)^T\delta+
\frac{1}{2\eta}\delta^T\Big(\sum_iD_i\Big)\delta.
\]

其唯一解就是式 (1)。写成各调用的未加 learning rate 的 Adam 方向 \(u_i=D_i^{-1}m_i\)，对坐标 \(k\) 有

\[
\boxed{\delta_k^*=-\eta\sum_iw_{i,k}u_{i,k},\qquad
w_{i,k}=\frac{D_{i,kk}}{\sum_jD_{j,kk}}.}
\tag{16}
\]

这里的权重是逐坐标的 RMS 权重。若 early 的梯度 RMS 在某个坐标上较小，它在该坐标的归一化更新确实得到更小权重。这个条件可以直接从 optimizer state 检查；没有“早期位置必然小权重”的一般结论，也通常不存在一个对所有坐标都准确的标量 depth weight。

它为什么是这样的加权？把式 (8) 配方即可看见：共享解也是

\[
\delta_*=arg\min_\delta
\sum_i\|\delta-\delta_i^*\|_{D_i}^2,
\qquad\|v\|_{D_i}^2=v^TD_iv.
\tag{17}
\]

各层原本有自己的最优更新。tying 迫使它们接受同一个更新，偏离哪一层的建议更昂贵，应由原来那一层的度量决定。使用欧氏平均会把这些代价全部改成相同。

甚至可以精确写出 tying 在式 (8) 中增加的最小目标值：

\[
q_{\rm tied}^*-q_{\rm untied}^*
=\frac1{2\eta}\sum_i
\|\delta_i^*-\delta_*\|_{D_i}^2\geq0.
\tag{18}
\]

它度量的是各调用希望采取的更新在原 Adam 度量下有多不一致。

这与普通 Adam 有何区别？若每个调用使用相同 EMA 系数和时间索引，一阶矩相加等于总梯度的一阶矩。但两个分母不同：

\[
\begin{aligned}
D_{\rm ordinary,kk}
&=\sqrt{\operatorname{EMA}[(\sum_i g_{i,k})^2]}+\epsilon,\\
D_{\rm inherited,kk}
&=\sum_i\big(\sqrt{\operatorname{EMA}[g_{i,k}^2]}+\epsilon\big).
\end{aligned}
\tag{19}
\]

EMA 可换成相应的 bias-corrected 加权平均。相同权重下，Minkowski 不等式给出不含 epsilon 的 \(D_{\rm ordinary,kk}\leq D_{\rm inherited,kk}\)。两种方法的坐标尺度与抵消响应不同，不能简单视为同一个 optimizer；平均或求和约定带来的全局系数则可并入 learning rate。

式 (1) 是“继承逐调用 Adam 几何”的一个明确候选，不是声称它已经比普通 Adam 更好。若评估它，需要显式控制整体更新尺度。保留各调用二阶矩有理论意义，但这个推导支持的合并方式是式 (16)，而不是任意归一化后加权。

## 7. 为什么“untied 时得到 Adam”还不足以唯一决定 sharing

一个容易忽略的事实是：同一个 untied optimizer 可以有不止一种局部优化表述，它们在 tying 后可能不同。

关闭 EMA，并对非零梯度坐标忽略 epsilon。元素 max 预算在 untied 时给出 \(-\eta\operatorname{sign}(g_i)\)；式 (8) 取 \(D_i=\operatorname{diag}(|g_i|)\) 时，也给出完全相同的 untied 更新。但 tying 后：

| 继承的 untied 更新几何 | tied 更新，逐坐标 |
|---|---|
| 元素最大位移预算 | \(-\eta\operatorname{sign}(\sum_i g_i)\) |
| 自适应二次更新代价 | \(-\eta(\sum_i g_i)/(\sum_i|g_i|)\) |

例如两个调用在某一坐标给出 \(g_1=9,g_2=-1\)。untied 时两者各自走 \(-\eta,+\eta\)。hard tying 后，第一种几何给出 \(-\eta\)，第二种给出 \(-0.8\eta\)，而归一化后等权平均给出 0。

后一种共享更新包含一个由梯度一致程度决定的缩放：同号时绝对值为 \(\eta\)，抵消时自动变小。这个现象不依赖调用的位置或 distance。

因此，想从 Adam / Muon 推出共享算法，需要同时说明：untied 的更新问题是什么，以及 tying 时到底保留哪一个预算或度量。仅证明某个公式在 untied 极限等于已知 optimizer，并不足以确定它的共享版本。

## 8. 连续过渡：用 soft tying 连接独立更新和共享更新

还可以把等式约束放松成“更新之间允许偏离，但要付代价”。在同一 tied 前向点，考虑

\[
\begin{aligned}
\min_{\delta_1,\ldots,\delta_T,z}\quad
&\sum_i\left[m_i^T\delta_i+
\frac{1}{2\eta}\delta_i^TD_i\delta_i\right]\\
&+\frac{\tau}{2\eta}\sum_i\|\delta_i-z\|_2^2.
\end{aligned}
\tag{20}
\]

它对应在展开网络上对各参数副本的分歧做二次惩罚：在当前副本相同时，对更新后的副本保留该惩罚就得到式 (20)。\(\tau=0\) 时是独立 Adam 更新；\(\tau\to\infty\) 时强制完全共享。

对于 \(\tau>0\)，一阶条件给出

\[
\delta_i=(D_i+\tau I)^{-1}(\tau z-\eta m_i),
\qquad z={1\over T}\sum_i\delta_i.
\]

从而

\[
z_\tau=-\eta
\left[\sum_iD_i(D_i+\tau I)^{-1}\right]^{-1}
\sum_i(D_i+\tau I)^{-1}m_i.
\tag{21}
\]

两个极限是

\[
\begin{aligned}
\lim_{\tau\to0^+}z_\tau
&=-{\eta\over T}\sum_iD_i^{-1}m_i,\\
\lim_{\tau\to\infty}z_\tau
&=-\eta\Big(\sum_iD_i\Big)^{-1}\sum_i m_i.
\end{aligned}
\tag{22}
\]

第一行是各调用 Adam 建议的欧氏平均；第二行是保留原几何的 hard-tying 解。这提供了一个连续、无 depth 参数的过渡。

但有限 \(\tau\) 时各 \(\delta_i\) 仍不同，因此式 (20) 本身描述允许副本偏离的网络。在始终 hard-shared 的网络上只采用 \(z_\tau\)，是利用它构造的新合并规则，不能声称已经精确求解 hard-sharing 问题。在 \(\tau=0\) 处 \(z\) 本身未被约束，第一行指右侧极限。

## 9. Early 权重和深度究竟从哪里进入

这些推导保留了深网络的反向传播，深度已经通过 \(G_i\)、\(m_i\)、\(D_i\) 和架构预算进入。一个统一的 \(\rho\) 不是必要条件。

在相同形状、相同谱范数预算的 Muon 中，tying 本身不产生额外的 early 系数。若要推导不同系数，需要额外说明新的几何或目标，例如根据不同调用的输入激活分布定义不同的算子约束。仅仅把层编号代入一个衰减函数，不是上述约束问题的推论。

在继承 Adam 度量的方案中，early 是否降权取决于式 (16) 的 RMS 比值。它可以在某些坐标降权，在另一些坐标保持或增大；从一个标量梯度范数，无法确定所有坐标上的结果。

更精细的模块组合理论可以引入各 block 的实际 sensitivity、输入尺度和预算分配，帮助把局部更新约束与整体网络变化联系起来。这些量不必是跨所有层相同的收缩系数，也不自动产生 inverse-distance 权重。[Modular Duality，模块组合定义](https://arxiv.org/html/2410.21265v1#S3.SS4)

若只知道“各调用对应同一份参数”，没有额外的状态或架构差异，上述 tying 操作对调用标签的重排不变。它无法凭标签认出哪一个叫 early，并凭空给出一个确定的 depth 衰减指数。

## 10. 数值核对与研究上可以保留的结论

本次核对使用真实的 12 层、宽度 6 的残差网络，block 为 \(h\leftarrow h+0.15\tanh(Wh+0.2x)\)，loss 为交叉熵。网络 loss 非线性、非二次。把同一个参数复制为 12 份并在相同前向点计算梯度，再与真正共享的反向传播比较。

| 核对项 | 数值 |
|---|---:|
| 共享前向与展开前向的 loss 差 | 0 |
| 各调用梯度之和与共享梯度的最大差 | \(1.11\times10^{-16}\) |
| untied Muon 达到对偶范数下界的误差 | \(5.42\times10^{-20}\) |
| tied Muon 达到对偶范数下界的误差 | \(5.42\times10^{-20}\) |
| Adam tying 解的一阶条件残差 | \(6.78\times10^{-21}\) |
| soft-tying 闭式解与完整线性方程解的最大差 | \(5.93\times10^{-21}\) |

Muon 在 \(\eta=10^{-4}\) 时，untied 和 tied 的一步实际 loss 都下降。这只核对局部公式，不比较长期训练性能。Adam 的验证使用显式构造的正对角状态；未把它冒充成训练中拟合得到的最佳度量。

现在可保留的研究判断是：应先明确想继承的 untied 更新几何，再研究 tying 后的最优解。Muon 的标准几何给出先求和后正交化；Adam 的逐调用几何给出 RMS 加权的更新共识；归一化后等权合并可作为独立建议的欧氏投影或 soft-tying 极限来理解。它们是可以区分、可以验证的不同 formulation。

这次推导没有建立 \(1/n\)、\(\rho^3\) 或任何固定 early 降权律。它给出的新分析对象是调用间的更新兼容程度、继承度量后的加权共识，以及从 soft tying 到 hard tying 的连续过渡。
