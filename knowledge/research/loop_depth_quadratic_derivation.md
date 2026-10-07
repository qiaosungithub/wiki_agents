# 从 Adam 的局部优化形式到共享 loop 的梯度权重

2026-09-10。独立推导笔记，回应研究者要求的“从同一个优化问题出发，先做二维推导”。

已读 [research idea page](normalize_then_sum.md) 和本地 [原报告](../../../perloop_gradient_merge.html)。原报告中的训练数值未重新复现；本笔记的二维闭式解和数值检查是独立计算的。这里的 early 指前向位置较早、距最终 loss 较远，不指训练初期。

主要结果：在下面明确给出的两方向模型中，归一化后的 early/late 最优权重比为

\[
\frac{s_E}{s_L}=\frac{\rho(\rho^2-c)}{1-\rho^2c},
\]

其中 \(c\) 是两个垂直于残差的输出扰动的余弦，而非两个参数梯度的余弦。原报告的 \(\rho^3\) 是 \(c=0\) 的特例；梯度正交不能推出 \(c=0\)。保留完整的二阶模型即可得到这个结果，不需要先删掉某类曲率。

## 1. 一个贯穿全文的优化问题

固定当前点的一阶量 \(m\) 和正定度量 \(M\)，考虑

\[
\min_\Delta\;m^T\Delta+\frac{1}{2\eta}\Delta^TM\Delta.
\tag{1}
\]

一阶条件给出唯一解

\[
\Delta_*=-\eta M^{-1}m.
\tag{2}
\]

它也与下面的椭球约束问题有相同方向：

\[
\min_\Delta m^T\Delta\quad
\text{s.t.}\quad \tfrac12\Delta^TM\Delta\leq\varepsilon,
\]

\[
\Delta_*=-\sqrt{\frac{2\varepsilon}{m^TM^{-1}m}}M^{-1}m
\quad(m\ne0).
\tag{3}
\]

所以除以曲率的动机是：在由曲率衡量的同一更新预算下，取得最大一阶下降。若 \(M=H\succ0\)、\(m=g\)，则得到 Newton 方向。在 Hessian 特征基中，每个分量是 \(-g_k/h_k\)。一般坐标下应写 \(-H^{-1}g\)，不是逐元素除以任意 Hessian。

对于平方误差的局部输出线性化，\(H=J^TJ\) 是 Gauss–Newton 曲率；非线性网络的真实 Hessian 还包含残差乘网络二阶导的项。后文两个仿射 loop 的 loss 本身就是二次函数，Gauss–Newton 与真实 Hessian 完全相同。奇异或非正定情形需要阻尼等额外处理。

Adam 的精确局部表述是把式 (1) 中的量设为

\[
m=\widehat m_t,\qquad
M=D_t=\operatorname{diag}(\sqrt{\widehat v_t}+\epsilon),
\]

于是解就是 \(-\eta D_t^{-1}\widehat m_t\)，暂不含 weight decay。这里的“精确”指冻结当前 optimizer state 后的更新公式，不是声称 \(D_t\) 等于真实 Hessian。[Adam 原论文](https://arxiv.org/pdf/1412.6980) 用梯度一、二阶矩定义该更新。

一种能让 Adam 近似 Newton 的额外统计假设是：在对角二次模型中，样本梯度满足 \(g_{\xi,k}=h_ke_{\xi,k}\)，且各坐标 \(\mathbb E e_{\xi,k}^2=s^2\)。此时 \(\sqrt{\mathbb E g_{\xi,k}^2}=s h_k\)，两种更新方向一致。这个假设不是一般事实。若固定 \(J\)，而输出残差的原始二阶矩为 \(\mathbb E[r_\xi r_\xi^T]=\sigma^2I\)，梯度二阶矩反而与 \(J^TJ\) 成比例，Adam 用的是其对角的平方根。仅有残差噪声的协方差各向同性不足以推出这个等式。

原报告把“对角 Hessian”“坐标 sign 更新”“整层梯度除以范数”连续替换，这些不是一般等价的操作。以下先解决共同的二阶问题，再明确所比较的归一化方式。

## 2. 共享参数改变的是整个二阶问题

把每个调用临时看成独立副本。记输出对副本的 Jacobian 为 \(J_i\)，平方误差残差为 \(r\)，则

\[
g_i=J_i^Tr,\qquad H_{ij}=J_i^TJ_j.
\]

不共享时的局部问题是

\[
\min_{\Delta_1,\ldots,\Delta_T}
\sum_i g_i^T\Delta_i+
\frac12\sum_{i,j}\Delta_i^TH_{ij}\Delta_j.
\tag{4}
\]

共享时，在同一个式 (4) 上加约束 \(\Delta_i=\Delta\)。因此

\[
G=\sum_i g_i,\qquad J=\sum_iJ_i,\qquad
H_{\rm shared}=\sum_{i,j}H_{ij}=J^TJ,
\]

\[
\Delta_*=-H_{\rm shared}^{-1}G.
\tag{5}
\]

只保留 \(\sum_iH_{ii}\) 会漏掉跨调用的二阶项。即使使用这个 block diagonal 近似，解仍然是 \(-(\sum_iH_{ii})^{-1}\sum_i g_i\)，而不是 \(-\sum_i H_{ii}^{-1}g_i\)。

若已获得分别归一化的方向 \(u_i\)，固定 \(U=[u_1,\ldots,u_T]\)，令 \(\Delta=-Us\)。式 (5) 在这些方向张成的空间中变成

\[
\min_s -b^Ts+\frac12s^TKs,
\qquad b=U^TG,\quad K=U^TH_{\rm shared}U.
\tag{6}
\]

当 \(K\succ0\) 时，\(s_*=K^{-1}b\)。这里可以用单位梯度，也可以用当前 Adam 的 \(D_i^{-1}m_i\) 作为 \(u_i\)；系数的数值随归一化约定改变。若 \(u_i\) 是线性相关的，最终更新可能唯一，但它的系数表示不唯一。要求非负权重则必须显式添加 \(s\geq0\)。

## 3. 保留原报告有价值的部分：沿残差与垂直残差的精确分解

令 \(\widehat r=r/\|r\|\)，并定义归一化方向在所有调用共同作用下的输出像

\[
Z=JU,\qquad Z_\perp=(I-\widehat r\widehat r^T)Z.
\]

因为 \(Z^Tr=b\)，式 (6) 的曲率可以精确分解为

\[
K=\frac{bb^T}{\|r\|^2}+C_\perp,
\qquad C_\perp=Z_\perp^TZ_\perp.
\tag{7}
\]

这是平方误差 Gauss–Newton 模型中的恒等式。沿残差的部分确实是秩一项；当 \(C_\perp\succ0\) 时，Sherman–Morrison 给出

\[
s_*=
\frac{C_\perp^{-1}b}
{1+b^TC_\perp^{-1}b/\|r\|^2}.
\tag{8}
\]

因此原报告“沿残差的秩一项只影响总尺度”这个观察有价值。真正需要检验的是它随后对 \(C_\perp\) 做的对角近似，以及是否遗漏了自身调用也可能产生的垂直残差分量。

梯度正交只约束 \(g_i^Tg_j\)。它不约束 \(Z_{\perp,i}^TZ_{\perp,j}\)。如果输出只有二维，垂直残差空间只有一维；两个非零 collateral 像只能同向或反向，不可能正交。此时 \(C_\perp\) 秩至多为一，不能直接使用要求其可逆的式 (8)，应求解完整式 (6)。

## 4. 严格二维、两个 loop 的可实现模型

考虑共享二维参数的仿射循环

\[
h_1=Ah_0+\theta,\qquad h_2=Ah_1+\theta,
\qquad h_0=0,\qquad
L(\theta)=\tfrac12\|h_2+e_1\|^2.
\tag{9}
\]

在 \(\theta=0\) 处，\(r=e_1\)。最近调用的 \(J_L=I\)，较早调用的 \(J_E=A\)。取

\[
A_-=\rho\begin{pmatrix}0&1\\-1&0\end{pmatrix},
\qquad 0<\rho<1.
\tag{10}
\]

它满足 \(\|A_-\|_2=\rho\) 且 \(A_-^TA_-=\rho^2I\)，因此满足严格的收缩、各向同性条件。两个梯度为

\[
g_L=e_1,\qquad g_E=\rho e_2,
\]

严格正交。分别除以梯度范数后，\(u_L=e_1,u_E=e_2\)。在无噪声、冻结矩估计的特殊情形，分别做 Adam 也给出这两个方向，忽略 \(\epsilon\) 的影响；一般 Adam 则须使用式 (6) 中的实际输出。

令 \(\Delta=-s_Le_1-s_Ee_2\)。下降方向的输出像为

\[
(I+A_-)(s_Le_1+s_Ee_2)
=(s_L+\rho s_E)e_1+(-\rho s_L+s_E)e_2.
\]

同一个真实 loss 的完整二次问题因此为

\[
q(s)=-(s_L+\rho s_E)
+\frac12\left[(s_L+\rho s_E)^2+(-\rho s_L+s_E)^2\right].
\tag{11}
\]

两种交叉项恰好抵消，所以

\[
K=(1+\rho^2)I,\qquad
s_*={1\over1+\rho^2}\begin{pmatrix}1\\\rho\end{pmatrix},
\qquad \boxed{s_E/s_L=\rho}.
\tag{12}
\]

early 相对分别归一化后等权的 1 应当降低到 \(\rho\)。在这个模型中，原始梯度直接求和已经具有正确方向。

如果把式 (11) 的 collateral 能量

\[
(-\rho s_L+s_E)^2
=\rho^2s_L^2+s_E^2-2\rho s_Ls_E
\]

近似为 \(\rho^2s_L^2+s_E^2\)，才会得到 \(s_E/s_L=\rho^3\)。原报告 A1–A4 没有排除被删去的最后一项。这个例子也满足自身调用的输出像沿残差同向，因此增加“承诺项相干”仍不足以推出 \(\rho^3\)。

这里共享的是加性参数。对一般共享 block，局部扰动满足 \(\delta h_t=A_t\delta h_{t-1}+B_t\Delta\)；当 \(A_t\approx A\)、\(B_t\approx I\) 时得到同样的局部 Jacobian。将本例用于实际共享权重矩阵，需要检查 \(B_t\) 是否近似稳定，不能只测下游 \(A_t\) 的收缩。

## 5. 两方向通式：什么时候是 rho，什么时候是 rho cubed

保留 \(g_L=e_1,g_E=\rho e_2\)，假设两个自身调用的输出像为 \(e_1,\rho e_1\)。两个跨调用像垂直于残差，范数分别为 \(\rho,1\)，余弦为 \(c\in[-1,1]\)。完整问题是

\[
q(s)=-(s_L+\rho s_E)
+\frac12\left[(s_L+\rho s_E)^2+
\rho^2s_L^2+s_E^2+2\rho c s_Ls_E\right].
\tag{13}
\]

即

\[
K=\begin{pmatrix}
1+\rho^2&\rho(1+c)\\
\rho(1+c)&1+\rho^2
\end{pmatrix},\qquad b=\begin{pmatrix}1\\\rho\end{pmatrix}.
\]

对于 \(0<\rho<1\)，这个矩阵对所有 \(c\in[-1,1]\) 正定。直接求逆得

\[
\boxed{\frac{s_E}{s_L}=
\frac{\rho(\rho^2-c)}{1-\rho^2c}}.
\tag{14}
\]

| collateral 相关性 | 最优归一化权重比 | 解释 |
|---|---:|---|
| \(c=-1\) | \(\rho\) | collateral 相互抵消；式 (9)–(12) 的二维旋转例子 |
| \(c=0\) | \(\rho^3\) | collateral 不相关；原报告额外需要的假设 |
| \(c=\rho^2\) | \(0\) | 最优方向只保留最近调用 |
| \(c=1\) | \(-\rho\) | collateral 同向；最优解通过负系数消除它 |

该比值随 \(c\) 单调下降。在本节的全部假设下，最大值为 \(\rho<1\)，所以确实可以证明 early 不应与 late 等权归一化。若添加非负约束，则最优比值为式 (14) 与 0 的较大者。这个结论依赖本节的具体几何结构，不是任意 loop 的结论。

严格二维输出中只有 \(c=\pm1\)。参数保持二维、输出扩为三维后，可实现任意 \(c\)：

\[
J_L=\begin{pmatrix}1&0\\0&1\\0&0\end{pmatrix},\qquad
J_E=\rho\begin{pmatrix}0&1\\c&0\\\sqrt{1-c^2}&0\end{pmatrix},\qquad r=e_1.
\]

两者仍分别满足 \(J_L^TJ_L=I\)、\(J_E^TJ_E=\rho^2I\)。也可以通过随机样本的 collateral 交叉项均值为零来得到式 (13) 的 \(c=0\) 期望模型。

加入同一个参数空间阻尼 \(\lambda\|\Delta\|^2/2\) 后，公式变为

\[
\frac{s_E}{s_L}=
\frac{\rho(\rho^2+\lambda-c)}{1+\lambda-\rho^2c}.
\tag{15}
\]

例如 \(c=0\) 时，从无阻尼的 \(\rho^3\) 连续趋向大阻尼的 \(\rho\)。因此只报告一个固定指数，也会隐藏 trust region / damping 的影响。

## 6. 负系数可以是精确最优，并非必然是假象

在式 (9) 中改用收缩反射

\[
A_+=\rho\begin{pmatrix}0&1\\1&0\end{pmatrix}.
\]

梯度仍为 \(g_L=e_1,g_E=\rho e_2\)，所有梯度范数和正交关系与旋转例子完全相同。但现在 \(c=1\)，精确解为

\[
s_*={1\over1-\rho^2}\begin{pmatrix}1\\-\rho\end{pmatrix},
\qquad L(\theta+\Delta_*)=0.
\]

这是全局凸二次 loss 的精确最优解，没有局部二阶近似误差。原报告第 6 节中的负系数在特定训练过程是否不稳，需要另行验证；不能从负号本身推出“假象”。

## 7. 多个 depth：原报告的公式需要哪些额外假设

对一般 loop，距离最终 loss 越远的调用，其 Jacobian 为

\[
J_t=A_T\cdots A_{t+1}B_t.
\]

即使每个 \(A_t\) 都收缩，也不能只据此断言 \(\|g_t\|\propto\rho^{T-t}\)；局部参数 Jacobian \(B_t\)、残差方向和奇异向量都可能随调用位置变化。

如果进一步假设：各梯度方向正交，\(\|g_d\|\propto\rho^d\)，调用 \(d\) 对任意单位参数位移的输出增益为 \(\beta\rho^d\)，自身调用的输出像沿残差，且所有相关 collateral 像的交叉项可以忽略，那么式 (7) 中

\[
b_d\propto\rho^d,\qquad
(C_\perp)_{dd}\propto S-\rho^{2d},\qquad
S=\sum_{d=0}^{T-1}\rho^{2d}.
\]

式 (8) 因而给出

\[
s_d\propto\frac{\rho^d}{S-\rho^{2d}},
\qquad
a_d\propto\frac{1}{S-\rho^{2d}},
\tag{16}
\]

其中 \(s_d\) 乘在单位方向上，\(a_d\) 乘在原始梯度上。原报告这个公式可以作为上述附加假设下的模型解。有限深度的精确式是 (16)，不是严格的 \([1,\rho^3,\rho^4,\ldots]\)。

如果保留相关性，则应回到 \(s\propto C_\perp^{-1}b\)，或在 \(C_\perp\) 奇异时直接求解式 (6)。如果梯度方向不正交，\(b_d=u_d^TG\) 也不能替换为 \(\|g_d\|\)。

这些公式都没有推出 \(1/(d+1)\) 是普遍最优。wiki 中的 inverse-distance 权重仍是经验选择；要为其建立理论，需要新的、可检验的 Jacobian 或噪声统计假设。

## 8. 原报告还需核对的两处数学表述

原报告第 10 节称 early 的独立部分在梯度正交时对 loss 无一阶贡献。但在它自己的正交假设下

\[
G^Tg_E=\|g_E\|^2>0.
\]

无一阶贡献的是某个跨调用输出像，不是 early 梯度方向的全部作用。

附录写子空间 Newton 求解 \(Ca=(\|g_i\|^2)_i\)。若以 \(V=[g_1,\ldots,g_T]\) 为原始梯度方向矩阵，正确的方程是

\[
(V^THV)a=V^TG.
\tag{17}
\]

只有梯度正交时，右端才等于各梯度范数平方。原报告表 5 自己报告的 \(g_i^TG/\|g_i\|^2\) 可达 2.47。因此需要检查原脚本的真实实现，才能判断所谓“精确 Newton”和效率上限是否算对。本笔记没有取得并执行其 scratchpad 脚本。

此外，式 (6) 的 \(u_i\) 若不是单位向量，系数就不是实际位移；普通 GD 的原始梯度求和方向也不能直接标成字面 Adam 或 Muon 的最终方向。分析必须固定 optimizer transformation 后再比较。

## 9. 独立数值核对及下一步可测量量

二维旋转例子取 \(\rho=0.5\)，起始 loss 为 0.5。每种方向都使用它自己的解析最优标量步长：

| 归一化后的 early/late 比值 | 最终真实 loss |
|---:|---:|
| 1，分别归一化后等权 | 0.05 |
| 0.5，完整二阶最优 | 0 |
| 0.125，原报告的 \(\rho^3\) | 0.055384615 |
| 0，只取最近调用 | 0.1 |

旋转例子的最优更新为 \((-0.8,-0.4)\)。反射例子的精确最优更新为 \((-4/3,2/3)\)，loss 为零，而仅用最近调用的最优 loss 为 0.1。

对 5 个 \(\rho\)、21 个 \(c\)、3 个阻尼值，共 315 个组合，用显式 Jacobian 构造 \(H\)，比较线性方程解和式 (15)，最大比值误差为 \(1.33\times10^{-15}\)。这核对了本笔记的闭式公式，不验证任何真实模型上的经验效果。

若下一步在真实模型上检验这条理论，关键量是 \(b=U^TG\) 和 \(C_\perp\) 的相关结构。仅测相邻梯度范数比和梯度余弦不足以区分本笔记两个二维例子。原报告的 \(\rho^3\) 需要 collateral 交叉项近似为零，而非仅仅梯度正交。对非平方误差，应先用输出 loss 的正半定曲率对输出空间加权，再构造对应的 Gauss–Newton 量。

标准二次模型与椭球最速下降的背景见 [Boyd 与 Vandenberghe，Convex Optimization，第 9 章](https://web.stanford.edu/~boyd/cvxbook/bv_cvxbook.pdf)。以上 loop 例子及相关性公式为本笔记的独立推导。
