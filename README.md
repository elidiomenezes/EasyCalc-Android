# EasyCalc for Android

An Android port of **EasyCalc 1.25**, the GPL scientific and graphing calculator originally written for Palm OS.

This repository is at the first executable milestone. It currently provides an offline native Android calculator with:

- algebraic expression parsing with operator precedence;
- scientific functions and constants;
- variables (`rate=2.5`, then `rate*10`);
- `ANS`, factorial, powers and degree/radian modes;
- an on-device calculation history;
- no network permission, ads, analytics or account.

The untouched EasyCalc 1.25 source release remains available from the original SourceForge project. Palm UI, database and memory APIs are being isolated progressively; this avoids hiding a full rewrite behind the word "port" and keeps provenance auditable.

## Build

```sh
gradle assembleDebug
```

The APK is written to `app/build/outputs/apk/debug/app-debug.apk`. Every pull request runs the engine smoke tests and a clean Android debug build.

## Roadmap

1. Expression engine and calculator shell (current)
2. Persistent definitions and preferences
3. Function graphing and table mode
4. Matrices, complex numbers and numerical solvers
5. Progressive integration of portable original C modules through JNI

## License and provenance

EasyCalc is Copyright (C) 1999-2007 Ondrej Palkovsky and contributors. The original program is licensed under GNU GPL version 2 or later. This Android port is distributed under the same terms (`GPL-2.0-or-later`). See the [official GPL 2.0 text](https://www.gnu.org/licenses/old-licenses/gpl-2.0.html).

Original release archive: <https://sourceforge.net/projects/easycalc/>
