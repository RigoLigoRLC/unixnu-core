# AdrenoMetal

AdrenoMetal 通过 `MTLAddDevice` 发布 Metal 设备。metal2vulkan 将 AIR 翻译为 SPIR-V，Turnip 完成编译，并向 [Adreno740](/zh/drivers/adreno740) 提交任务。固件、电源投票和显示集成由设备仓库提供。

## 渲染和接口

| 项目 | 当前行为 |
| --- | --- |
| MSAA 策略 | 所有客户端的纹理、管线和渲染通道默认使用单采样。resolve 目标接收渲染结果，load 和 store-and-resolve 保留源内容。`NATIVE_METAL_SINGLE_SAMPLE=0` 让进程保留请求的采样数，`1` 强制单采样。 |
| Heap 资源 | buffer 和 texture 的 `makeAliasable` 归还 heap 区间。 |
| 纹理通道 | 纹理描述符和 view 保留全部四个 swizzle，包括显式零和一。 |
| 复制和光栅状态 | blit 覆盖指定 mip 和 slice 范围。viewport、scissor 传递完整数组，最多 16 项。 |
| 压缩纹理输入 | 长度为零的 no-copy 压缩纹理按 DroidVM 布局推导大小，使用结束后调用所有者的 deallocator。 |
| 函数 | 函数常量字典提供名称、索引和类型。函数及计算管线的完成回调返回结果。`specializedName` 用作导出名称，源码查找保留原函数名。 |
| 常量表 | 超过 4 KiB 的动态索引常量表使用共享常量存储。常量指针转换和 GEP 表达式保留偏移。 |
| 内存统计 | 设备用量统计池、独立和导入分配。纹理大小来自实际 backing allocation。建议工作集为 RAM / 4，上限 2 GiB。 |
| 队列容量 | `newCommandQueueWithMaxCommandBufferCount:` 使用 runtime 的未完成缓冲数量限制。未提交缓冲销毁时释放名额，已提交缓冲在完成回调返回后释放名额。 |

渲染通道编码失败时仍返回 encoder，通过 command buffer 报错，支持缓存 encoder 方法的调用方。

## 缓存和优先级

相同 UID 的客户端在可写时共用账户 home 下的 `Library/Caches/org.unixnu.metal`。沙箱限制写入时使用私有缓存。`NATIVE_METAL_SHARED_CACHE_DIR` 可指定共享目录，空值关闭共享。缓存覆盖 Apple 前端结果、runtime 产物和 Turnip IR3。并发导入使用独立临时文件，管线日志按进程分开。

同一进程的 Metal 逻辑队列共用一个 Vulkan 队列和内核队列。前端汇总存活队列的当前请求，采用其中最高的优先级；队列降级或销毁后撤回提升。getter 返回各队列自身的请求，setter 返回后端是否接受。内核根据任务的 GPU role 选择前台或后台优先级，策略不使用进程名。


已空闲的自有图像内存可供池化和独立图像复用。额外缓存按设备合计上限为 256 MiB，十秒后过期。至少 256 KiB 的普通自有内存可交给现有后台线程释放，待回收队列上限为 128 MiB；分配失败时先释放排队内存，再重试。导入内存和外部所有者回调保留原有释放顺序。首次使用仍可能需要准备新内存页。

## 构建和检查

在解析后的 iOS 27 目标构建树中执行：

板级构建向 Turnip 和插件提供同一份 `NativeAdrenoABI.h`。Turnip 按查询到的
ABI 版本选择提交记录：版本 1 为 16 个 IB、416 字节，版本 2 为 128 个 IB、
3104 字节。诊断 mailbox 保留 16 个 IB 的记录。host-import 只有收到内核
移除 GPU 映射的成功确认后，才释放调用者持有的页面。

Darwin 设备声明支持缓存一致性内存时，Turnip 将其作为资源、heap 和内部命令
存储的默认类型。CPU 映射使用 write-back，内核根据分配对象或导入页面的实际
属性建立 GPU 映射。在统一内存 GPU 上，Metal Shared、WriteCombined 提示、
Private 资源以及实际分配存储的 Memoryless 附件均优先选择缓存一致性内存。
前端查询识别硬件一致性和内核负责的可见性处理；两者都会移除提交和完成路径
中的 IOSurface 刷新范围收集及用户态缓存操作。

SM7325 适配将资源声明、render memory barrier 和 fence 的阶段参数传给
metal2vulkan。编码时累加访问摘要，提交时只为存在 CPU 消费者的分配对象
导出 GPU 写入。Turnip 的 Darwin 异步扩展把 timeline 依赖和输出时间点交给
内核调度器，CPU 等待在所需时间点上睡眠。显示驱动持有 IOSurface backing
的读占用，直到 DPU 切换到下一张表面。

`unixnu-sm-t733` 分支保留上述提交与同步优化，以及系统 BGRA8 sRGB 格式
策略。`unixnu-sm-t733-apple3` 分支增加 Apple3 前端、编译器和格式实现。
设备的两个分支分别固定对应的 core、SoC 和 Metal 版本。

SM7325 桥接使用 metal2vulkan development 提交
`624bab3918de5b978e1101517abca2b4fa426565`，补丁顺序由
`AdrenoMetal/bridge/patches/series` 记录。本机资源可见性和缓存一致性内存
策略接入新运行时的 fence 阶段模型。

设备查询按 selector 和参数缓存，前端关闭 no-copy 重绑所需的编码器回放记录。
运行时接受纹理布局时，host-page 纹理直接使用导入内存。对于尺寸未填满 GMEM
块的外部线性附件，Turnip 使用 draw load 和 2D store，传输只覆盖所属行跨度
内的有效像素。

`NATIVE_ADRENO_FRAME_TRACE=0` 与 `NATIVE_ADRENO_PIPELINE_JOURNAL=0` 默认关闭
逐命令追踪和管线文件日志，保留周期读取的内存统计。前端错误与 host-import
释放错误各自最多输出 32 条。

```sh
python3 scripts/build-turnip-darwin.py --target ios27
python3 scripts/build-adreno-metal-plugin.py --target ios27
python3 scripts/check-native-metal-frontend-host.py
```

正常构建应用记录在仓库中的翻译器、Turnip 补丁，并开启 Mesa 磁盘 shader cache。主机检查覆盖渲染像素、resolve、资源回收、swizzle、复制、回调、队列容量及优先级汇总。上机验证项目是并发客户端下的帧间隔和抢占行为。

设备输入和打包方式见 [GPU 适配流程](/zh/porting/gpu)。

帧诊断保留分配、命令、完成处理及 GPU、显示时间线，像素抓取关闭。使用方法见 [GPU 帧诊断](/zh/porting/gpu-diagnostics)。

`sheng-wallpaper-freeze=1` 用于隔离壁纸渲染。名字包含 Poster 的渲染进程首次成功绘制并保存至少 200 万像素的 IOSurface 后，保留该输出，拦下后续 command buffer 的 runtime 提交。被拦下的缓冲保持已 commit、未调度状态，继续持有资源和队列名额；此前已提交的工作正常完成。PosterBoard、backboardd 和其他客户端继续提交。此模式默认关闭。

细分延迟记录标出慢编码调用、回调入口地址和资源析构耗时。内核对渲染、编码和完成线程的采样关联上游等待。
