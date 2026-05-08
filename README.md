# 10年结清·动态买房推算器

一个基于 Python + Tkinter 的房贷计算器，帮助你评估在不同贷款方案下，能否在10年内结清房贷。

## 功能特性

- **双模式计算**：按月供反推房价 / 按房价正算月供
- **10年结清判定**：根据收入、开销、公积金等参数，判断10年内能否还清
- **20年完美卡点**：自动反推使20年贷款"刚好一分不剩"的房价
- **多贷款年限对比**：同时展示10/15/20/25/30年贷款方案
- **额外月供支持**：可设定每月额外还款金额，加速还贷

## 使用方式

### 直接运行

```bash
python marginUI.py
```

### 打包为 exe

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name "房贷计算器" marginUI.py
```

打包后的 exe 位于 `dist/` 目录下。

## 项目结构

```
├── calc.py          # 核心计算逻辑（纯函数，无UI依赖）
├── marginUI.py      # Tkinter GUI 界面
├── test_calc.py     # 单元测试
└── requirements.txt
```

## 运行测试

```bash
pip install pytest
pytest test_calc.py -v
```

## License

MIT
