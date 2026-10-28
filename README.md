# Xplane MFD Calculations
This repository contains flight calculation code for data published by the X-Plane [Web API](https://developer.x-plane.com/article/x-plane-web-api/). It demonstrates the [**Joint Strike Fighter Air Vehicle C++ Coding Standards**](https://www.stroustrup.com/JSF-AV-rules.pdf) (JSF AV C++). The `compliant/` directory contains code with numerous JSF Standard fixes, while `non-compliant/` contains multiple major standard violation examples.

<img width="1790" height="1132" alt="mfd_display" src="https://github.com/user-attachments/assets/c577fd40-6d1b-4e2a-a500-d3593338ee63" />

The main non-compliant code examples are marked with `REMOVE BEFORE FLIGHT` tags showing violations with:
1. **Exceptions** — *AV Rule 208*
2. **Recursion** — *AV Rule 119*
3. **Dynamic Memory Allocation** — *AV Rule 206*

<details>
<summary><strong>To follow JSF AV Style rules, the following `clang-format` style can be used:</strong></summary>
<code>{ BasedOnStyle: LLVM, ColumnLimit: 120, BreakBeforeBinaryOperators: None, IndentWidth: 4, TabWidth: 4, UseTab: Never, PointerAlignment: Left, ReferenceAlignment: Left, AlignAfterOpenBracket: Align, AlignOperands: DontAlign, AlignTrailingComments: true, AllowAllParametersOfDeclarationOnNextLine: false, BinPackParameters: AlwaysOnePerLine, BinPackArguments: false, AlwaysBreakAfterReturnType: None, AllowShortFunctionsOnASingleLine: InlineOnly, SpacesBeforeTrailingComments: 2, SpaceBeforeParens: ControlStatements, SpaceAfterCStyleCast: true, BreakTemplateDeclarations: Yes, AccessModifierOffset: -4, SpaceAfterTemplateKeyword: false, AlignConsecutiveAssignments: Consecutive, AlignConsecutiveDeclarations: { Enabled: false, AcrossEmptyLines: true, AcrossComments: true, AlignFunctionDeclarations: false }, BreakBeforeBraces: Custom, BraceWrapping: { AfterCaseLabel: true, AfterClass: true, AfterControlStatement: Always, AfterEnum: true, AfterFunction: true, AfterNamespace: true, AfterStruct: true, AfterUnion: true, AfterExternBlock: true, BeforeCatch: true, BeforeElse: true, BeforeLambdaBody: true, BeforeWhile: true, SplitEmptyFunction: true, SplitEmptyRecord: true, SplitEmptyNamespace: true } }</code>
</details>

## Build
```bash
# Build JSF-compliant version (default)
make

# Build non-compliant version
make non-compliant
```

## Run
```bash
# Launch the MFD (requires X-Plane with Web API)
./run_mfd.sh
```

## Calculators
Individual calculators can be run directly:

```bash
./wind_calculator 120 300 45
./flight_calculator 250 280 180 175 150 0.45 35000 34000 -500 65000 15 55 320 0.85
./turn_calculator 200 30 90
./vnav_calculator 35000 10000 100 450 -1800
./density_altitude_calculator 5000 25 150 170
```
