# AdrenoMetal

SM-T733 的 `unixnu-sm-t733` 主分支保留驱动优化和系统 BGRA8 sRGB 格式策略；
当前 `unixnu-sm-t733-apple3` 分支增加 Apple3 前端和格式实现。
设备分支固定对应的 core、SoC 和 Metal 版本。

先按[适配流程](/zh/porting/gpu)准备板级输入、修改源码、接入构建并逐步验证。

AdrenoMetal 通过 metal2vulkan 和 Turnip 提供 Metal 前端。它通过 `MTLAddDevice`
发布设备，翻译 AIR，并向内核 GPU 接口提交任务。

| 字段 | 值 |
| --- | --- |
| 仓库 | [UniXNU/AdrenoMetal](https://github.com/UniXNU/AdrenoMetal) |
| 实现 | A740/SM8550 图形栈和所选 OS ABI |
| 依赖 | Adreno740、Turnip、metal2vulkan、IOGPUFamily 和 IOSurface 接口 |
| 板级输入 | 固件、电源策略、内存布局、显示集成 |
| 已验证设备 | sheng |
| 运行时插件 | `NativeAdrenoMetal` |

sheng 已运行 GPU 合成桌面。导出的 pipeline cache 可在后续启动复用。桌面空闲时，
render server 会预编译系统镜像中的全部 Metal 库：payload 带有库列表
（`NativeAdrenoMetal.primelist`），以及一份 cryptex 中 QuartzCore 库的副本，因为
render server 的沙盒访问不到 cryptex 路径。120 Hz 下空闲桌面每 250 ms 提交约
6 个命令缓冲区，所以只有超过 8 个时预编译才会等待。日志 PR 行显示进度；sheng 上
162 个库已全部预编译。有列表时 render server 不扫描目录，并且只在显示空闲时读取
每个库。

无法编码的 render pass 仍返回 encoder，并拒绝其命令缓冲区：RenderBox 会缓存
encoder 的方法，不能接受 nil。每个进程的第一个问题由出错
的线程写入驱动的进程文本行。

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

参数编码器、间接命令缓冲区和细分描述符接入 runtime 的对应对象。默认采样
位置查询读取 Vulkan 的标准位置属性及 runtime 支持的采样数。iPadOS 17 的
Metal IO 队列沿继承的系统实现运行，使用桥接的 blit encoder、shared event
和稳定资源追踪标识。

PVRTC 采样使用 GPU 解码的 RGBA8 图像，上传和 blit 后刷新相应 mip 层。
深度 Min/Max resolve 可以在整数颜色附件中保存所选样本，再将位模式传送到
目标深度 aspect。这些实现属于 SM-T733 源码适配，构建身份和设备结果由设备
仓库记录。

设备查询按 selector 和参数缓存，前端关闭 no-copy 重绑所需的编码器回放记录。
带行间距的 render target 只有在高度是 4 的倍数、宽度向上取整至 16 像素后的
字节数不超过行距、最后一行不越过分配范围时，才直接别名原缓冲区；其余使用
shadow 图像。

`NATIVE_ADRENO_FRAME_TRACE=0` 与 `NATIVE_ADRENO_PIPELINE_JOURNAL=0` 默认关闭
逐命令追踪和管线文件日志，保留周期读取的内存统计。前端错误与 host-import
释放错误各自最多输出 32 条。

```sh
python3 scripts/build-turnip-darwin.py --target ios
python3 scripts/build-adreno-metal-plugin.py
```

运行时流程、发布命令和检查见 [Adreno740](/zh/drivers/adreno740)。
