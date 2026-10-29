#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PlainApp 定制补丁脚本（自适应版）
对 checkout 出的上游代码应用全部定制：
  1. 移除设置页官方板块（PDonationBanner / PExploreBanner）
  2. 新增"在最近任务中隐藏"开关（HideFromRecents）
  3. 关闭检测更新 / 捐赠卡片（AppFeatureTypeExt）
  4. 移除 LeakCanary（gradle 依赖 / debug manifest provider / 源码文件）
  5. 构建体积优化（release minify 开、shrinkResources 关；Cargo strip + opt）
  6. Rust core 依赖指向 plain-core-private
  7. 音频目录观察者（若上游保留 AudioCatalogObserver 体系则启用）
退出码：
  0   = 所有关键补丁均已应用
  非 0 = 关键补丁缺失（触发上游版本回退）
用法：python3 apply-patches.py [repo_root]
"""
import os
import re
import shutil
import sys

ROOT = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else ".")
PATCH_FILES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "files")

def P(*parts):
    return os.path.join(ROOT, *parts)

def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()

def write(p, s):
    with open(p, "w", encoding="utf-8") as f:
        f.write(s)

results = []          # (step, ok, note)
def record(step, ok, note=""):
    results.append((step, ok, note))
    status = "✅" if ok else ("⚠️" if note.startswith("SKIP") else "❌")
    print(f"{status} [{step}] {note}")

# ---------- 1. 复制新增文件 ----------
def copy_new_files():
    if not os.path.isdir(PATCH_FILES):
        record("copy-files", False, "patches/files 目录缺失")
        return False
    ok = True
    for base, dirs, files in os.walk(PATCH_FILES):
        for fn in files:
            src = os.path.join(base, fn)
            rel = os.path.relpath(src, PATCH_FILES)
            dst = P(rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
            print(f"   copied {rel}")
    # HideFromRecents 是关键项
    if os.path.exists(P("shared/src/commonMain/kotlin/com/ismartcoding/plain/platform/system/HideFromRecents.kt")) and \
       os.path.exists(P("shared/src/androidMain/kotlin/com/ismartcoding/plain/platform/system/HideFromRecents.android.kt")):
        record("copy-files", True, "新增文件已复制")
    else:
        record("copy-files", False, "HideFromRecents 文件缺失")
        ok = False
    # 上游 main 重构后已删除 AudioCatalogObserver 体系 → 移除观察者文件（否则 Kotlin 编译失败）
    obs = P("shared/src/commonMain/kotlin/com/ismartcoding/plain/rust/host/audio/AudioCatalogObserver.kt")
    if not os.path.exists(obs):
        obs_file = P("shared/src/androidMain/kotlin/com/ismartcoding/plain/platform/media/MediaStoreAudioCatalogObserver.kt")
        if os.path.exists(obs_file):
            os.remove(obs_file)
            print("   已移除 MediaStoreAudioCatalogObserver.kt（上游无 AudioCatalogObserver 体系）")
    return ok

# ---------- 2. AppFeatureTypeExt.kt：关闭更新检查/捐赠 ----------
def patch_feature_type():
    p = P("shared/src/commonMain/kotlin/com/ismartcoding/plain/platform/system/AppFeatureTypeExt.kt")
    if not os.path.exists(p):
        record("feature-type", False, "AppFeatureTypeExt.kt 不存在")
        return False
    s = read(p)
    orig = s
    # has(): 在函数开头注入 CHECK_UPDATES/DONATION 短路
    s = re.sub(
        r"fun AppFeatureType\.has\(\): Boolean = requiredCapability\(\)\?\.let\s*\{ it in getDeviceCapabilities\(\) \} \?: true",
        "fun AppFeatureType.has(): Boolean {\n"
        "    if (this == AppFeatureType.CHECK_UPDATES) return false\n"
        "    if (this == AppFeatureType.DONATION) return false\n"
        "    return requiredCapability()?.let { it in getDeviceCapabilities() } ?: true\n"
        "}",
        s,
    )
    s = re.sub(
        r"fun AppFeatureType\.has\(capabilities: Collection<Capability>\): Boolean = requiredCapability\(\)\?\.let\s*\{ it in capabilities \} \?: true",
        "fun AppFeatureType.has(capabilities: Collection<Capability>): Boolean {\n"
        "    if (this == AppFeatureType.CHECK_UPDATES) return false\n"
        "    return requiredCapability()?.let { it in capabilities } ?: true\n"
        "}",
        s,
    )
    if s != orig and "CHECK_UPDATES) return false" in s and "DONATION) return false" in s:
        write(p, s)
        record("feature-type", True, "CHECK_UPDATES/DONATION 已禁用")
        return True
    if "CHECK_UPDATES) return false" in s and "DONATION) return false" in s:
        record("feature-type", True, "已打过补丁（幂等）")
        return True
    record("feature-type", False, "has() 结构不匹配，未应用")
    return False

# ---------- 3. SettingsPage.kt：移除官方板块 ----------
def patch_settings_page():
    p = P("shared/src/commonMain/kotlin/com/ismartcoding/plain/ui/settings/SettingsPage.kt")
    if not os.path.exists(p):
        record("settings-page", False, "SettingsPage.kt 不存在")
        return False
    s = read(p)
    orig = s
    # 删除 import
    for imp in ["import com.ismartcoding.plain.ui.components.PDonationBanner\n",
                "import com.ismartcoding.plain.ui.components.PExploreBanner\n"]:
        s = s.replace(imp, "")
    lines = s.splitlines(keepends=True)
    # 策略1：整段删除 "if (AppFeatureType.DONATION.has()) { ... } else { ... }"（括号计数）
    def remove_block(start_line, all_lines):
        depth = 0
        k = start_line
        while k < len(all_lines):
            depth += all_lines[k].count("{") - all_lines[k].count("}")
            if depth == 0:
                return k + 1
            k += 1
        return len(all_lines)
    i = 0
    removed = False
    while i < len(lines):
        if "if (AppFeatureType.DONATION.has())" in lines[i]:
            end = remove_block(i, lines)
            lines = lines[:i] + lines[end:]
            removed = True
            break
        i += 1
    s = "".join(lines)
    # 策略2：仍残留 PDonationBanner/PExploreBanner（单 item 结构）则删其 item 块
    if "PDonationBanner" in s or "PExploreBanner" in s:
        lines = s.splitlines(keepends=True)
        new_lines = []
        i = 0
        while i < len(lines):
            if ("PDonationBanner" in lines[i] or "PExploreBanner" in lines[i]) and not removed:
                j = len(new_lines) - 1
                start = None
                while j >= 0:
                    if "item {" in new_lines[j] or "item{" in new_lines[j]:
                        start = j
                        break
                    j -= 1
                if start is None:
                    removed = True
                    i += 1
                    continue
                end = remove_block(start, lines)
                new_lines = new_lines[:start]
                i = end
                removed = True
            else:
                new_lines.append(lines[i])
                i += 1
        s = "".join(new_lines)
    if s != orig:
        write(p, s)
        banned = ("PDonationBanner" in s or "PExploreBanner" in s or "AppFeatureType.DONATION.has()" in s)
        record("settings-page", not banned, "官方板块已移除" if not banned else "残留未清干净")
        return not banned
    banned = ("PDonationBanner" in s or "PExploreBanner" in s or "AppFeatureType.DONATION.has()" in s)
    if not banned:
        record("settings-page", True, "已是定制状态（幂等）")
        return True
    record("settings-page", False, "banner 块结构未匹配，引用仍存在")
    return False

# ---------- 4. SettingsCardItems.kt：新增隐藏开关 ----------
def patch_settings_card():
    p = P("shared/src/commonMain/kotlin/com/ismartcoding/plain/ui/settings/SettingsCardItems.kt")
    if not os.path.exists(p):
        record("settings-card", False, "SettingsCardItems.kt 不存在")
        return False
    s = read(p)
    if "hide_from_recents" in s:
        record("settings-card", True, "开关已存在（幂等）")
        return True
    # import
    need = [
        "import androidx.compose.runtime.getValue\n",
        "import androidx.compose.runtime.mutableStateOf\n",
        "import androidx.compose.runtime.remember\n",
        "import androidx.compose.runtime.setValue\n",
        "import com.ismartcoding.plain.platform.system.isHideFromRecentsEnabled\n",
        "import com.ismartcoding.plain.platform.system.setHideFromRecents\n",
    ]
    for imp in need:
        if imp not in s:
            # 插入到同包 import 块末尾：放在最后一个 import 行之后
            lines = s.splitlines(keepends=True)
            last_import = max(i for i, l in enumerate(lines) if l.startswith("import "))
            lines.insert(last_import + 1, imp)
            s = "".join(lines)
    # 在函数末尾（最后一个 } 前）插入开关块
    rstrip = s.rstrip()
    if rstrip.endswith("}"):
        block = (
            "\n    VerticalSpace(16.dp)\n"
            "    PCard(modifier = Modifier.padding(horizontal = PlainTheme.PAGE_HORIZONTAL_MARGIN)) {\n"
            "        var hiddenFromRecents by remember { mutableStateOf(isHideFromRecentsEnabled()) }\n"
            "        PListItem(\n"
            "            title = stringResource(Res.string.hide_from_recents),\n"
            "            subtitle = stringResource(Res.string.hide_from_recents_desc),\n"
            "        ) {\n"
            "            Switch(\n"
            "                checked = hiddenFromRecents,\n"
            "                onCheckedChange = {\n"
            "                    hiddenFromRecents = it\n"
            "                    setHideFromRecents(it)\n"
            "                },\n"
            "            )\n"
            "        }\n"
            "    }\n"
            "}"
        )
        s = rstrip[:-1] + block + "\n"
        write(p, s)
        record("settings-card", "hide_from_recents" in s, "隐藏开关已添加")
        return "hide_from_recents" in s
    record("settings-card", False, "函数结构不匹配")
    return False

# ---------- 5. MainActivity.kt：启动应用隐藏 ----------
def patch_main_activity():
    p = P("shared/src/androidMain/kotlin/com/ismartcoding/plain/MainActivity.kt")
    if not os.path.exists(p):
        record("main-activity", False, "MainActivity.kt 不存在")
        return False
    s = read(p)
    if "applyHideFromRecents" in s:
        record("main-activity", True, "隐藏逻辑已存在（幂等）")
        return True
    # import（插到 import 块末尾）
    need = [
        "import com.ismartcoding.plain.platform.system.isHideFromRecentsEnabled\n",
        "import com.ismartcoding.plain.platform.system.applyHideFromRecents\n",
    ]
    for imp in need:
        if imp not in s:
            lines = s.splitlines(keepends=True)
            last_import = max(i for i, l in enumerate(lines) if l.startswith("import "))
            lines.insert(last_import + 1, imp)
            s = "".join(lines)
    # onCreate 开头注入（兼容 setContent 写法或 installSplashScreen/super.onCreate 写法）
    anchors = ["        setContent {", "    setContent {", "setContent {",
               "installSplashScreen(); super.onCreate(savedInstanceState)",
               "super.onCreate(savedInstanceState)"]
    anchor = next((a for a in anchors if a in s), None)
    if anchor:
        inject = (
            "        if (isHideFromRecentsEnabled()) {\n"
            "            applyHideFromRecents(this, true)\n"
            "        }\n"
        )
        s = s.replace(anchor, inject + anchor, 1)
        write(p, s)
        record("main-activity", "applyHideFromRecents" in s, "启动隐藏已注入")
        return "applyHideFromRecents" in s
    record("main-activity", False, "onCreate 锚点未找到")
    return False

# ---------- 6. MainApp.kt：音频目录观察者（条件性） ----------
def patch_main_app():
    p = P("app/src/main/java/com/ismartcoding/plain/MainApp.kt")
    if not os.path.exists(p):
        record("main-app", False, "MainApp.kt 不存在")
        return False
    s = read(p)
    # 仅当上游存在 AudioCatalogObserver 体系时启用（v3.3.x 有，main 重构后可能没有）
    obs = P("shared/src/commonMain/kotlin/com/ismartcoding/plain/rust/host/audio/AudioCatalogObserver.kt")
    if not os.path.exists(obs):
        record("main-app", True, "SKIP 上游无 AudioCatalogObserver 体系，跳过音频观察者")
        return True
    if "MediaStoreAudioCatalogObserver" in s:
        record("main-app", True, "已启用（幂等）")
        return True
    if "import com.ismartcoding.plain.platform.media.MediaStoreAudioCatalogObserver\n" not in s:
        lines = s.splitlines(keepends=True)
        last_import = max(i for i, l in enumerate(lines) if l.startswith("import "))
        lines.insert(last_import + 1, "import com.ismartcoding.plain.platform.media.MediaStoreAudioCatalogObserver\n")
        s = "".join(lines)
    s = s.replace("initializeApp()", "initializeApp(MediaStoreAudioCatalogObserver)")
    write(p, s)
    record("main-app", "MediaStoreAudioCatalogObserver" in s, "音频观察者已启用")
    return "MediaStoreAudioCatalogObserver" in s

# ---------- 7. 字符串词条 ----------
def patch_strings():
    def add(p, entries):
        if not os.path.exists(p):
            return False
        s = read(p)
        changed = False
        for name, val in entries:
            if f'name="{name}"' not in s:
                # 插在 <string name="logs"> 行后
                m = re.search(r'(<string name="logs">.*?</string>\n)', s)
                if m:
                    s = s.replace(m.group(1), m.group(1) + f'    <string name="{name}">{val}</string>\n')
                    changed = True
        if changed:
            write(p, s)
        return True
    ok1 = add(P("shared/src/commonMain/composeResources/values/strings_settings.xml"),
              [("hide_from_recents", "Hide from recent apps"),
               ("hide_from_recents_desc", "Hide this app from the recent apps list")])
    ok2 = add(P("shared/src/commonMain/composeResources/values-zh-rCN/strings_settings.xml"),
              [("hide_from_recents", "在最近任务中隐藏"),
               ("hide_from_recents_desc", "从最近任务列表中隐藏此应用")])
    if ok1 and ok2:
        record("strings", True, "中英文词条就绪")
        return True
    record("strings", False, "strings_settings.xml 缺失")
    return False

# ---------- 8. build.gradle.kts：压缩配置 + 去 LeakCanary ----------
def patch_build_gradle():
    p = P("app/build.gradle.kts")
    if not os.path.exists(p):
        record("build-gradle", False, "build.gradle.kts 不存在")
        return False
    s = read(p)
    orig = s
    # release minify 开 + shrinkResources 关（针对 githubRelease/release buildType 块）
    s = re.sub(r'(buildTypes\s*\{[\s\S]*?)(githubRelease|release)\s*\{',
               lambda m: m.group(1) + m.group(2) + " {", s, count=1) if False else s
    # 通用替换：所有 isShrinkResources = true -> false，isMinifyEnabled 保持（release 通常已是 true）
    s = s.replace("isShrinkResources = true", "isShrinkResources = false")
    s = s.replace("isShrinkResources=true", "isShrinkResources=false")
    # 注释 LeakCanary / work.multiprocess debug 依赖
    s = re.sub(r"debugImplementation\(libs\.leakcanary\.android\)",
               "// debugImplementation(libs.leakcanary.android)", s)
    s = re.sub(r"debugImplementation\(libs\.androidx\.work\.multiprocess\)",
               "// debugImplementation(libs.androidx.work.multiprocess)", s)
    if s != orig:
        write(p, s)
    if "isShrinkResources = false" in s and "leakcanary.android" in s and "// debugImplementation(libs.leakcanary.android)" in s:
        record("build-gradle", True, "shrinkResources=false + LeakCanary 已注释")
        return True
    if "isShrinkResources = false" in s:
        record("build-gradle", True, "shrinkResources=false（LeakCanary 行未完全匹配）")
        return True
    record("build-gradle", False, "配置未匹配")
    return False

# ---------- 9. debug manifest：删 LeakCanary provider ----------
def patch_debug_manifest():
    p = P("app/src/debug/AndroidManifest.xml")
    if not os.path.exists(p):
        record("debug-manifest", True, "SKIP 无 debug manifest")
        return True
    s = read(p)
    if "LeakCanaryKnownLeaks" not in s:
        record("debug-manifest", True, "无 LeakCanary provider（幂等）")
        return True
    # 删除注释 + provider 块
    s2 = re.sub(r'<!--[\s\S]*?LeakCanaryKnownLeaks[\s\S]*?-->\s*', '', s)
    if s2 == s:
        s2 = re.sub(r'\s*<provider\s+android:name="\.debug\.LeakCanaryKnownLeaks"[\s\S]*?/>', '', s)
    write(p, s2)
    record("debug-manifest", "LeakCanaryKnownLeaks" not in s2, "LeakCanary provider 已删除")
    return "LeakCanaryKnownLeaks" not in s2

# ---------- 10. 删除 LeakCanaryKnownLeaks.kt ----------
def remove_leakcanary_file():
    p = P("app/src/debug/java/com/ismartcoding/plain/debug/LeakCanaryKnownLeaks.kt")
    if os.path.exists(p):
        os.remove(p)
        record("leakcanary-file", True, "LeakCanaryKnownLeaks.kt 已删除")
        return True
    record("leakcanary-file", True, "无该文件（幂等）")
    return True

# ---------- 11. Cargo.toml：core 指向 private + strip + opt ----------
def patch_cargo():
    p = P("plain-rs/Cargo.toml")
    if not os.path.exists(p):
        record("cargo", False, "Cargo.toml 不存在")
        return False
    # 检测代码代际：上游 main 重构版（无 AudioCatalogObserver）→ 用 upstream-sync（上游最新 core）；
    # fork 基线（有 AudioCatalogObserver）→ 用 main（我们定制 core）
    obs = P("shared/src/commonMain/kotlin/com/ismartcoding/plain/rust/host/audio/AudioCatalogObserver.kt")
    core_branch = "upstream-sync" if not os.path.exists(obs) else "main"
    s = read(p)
    orig = s
    # plainhub → private（兼容带 ?branch=main 与不带两种写法）
    s = s.replace("https://github.com/plainhub/plain-core.git?branch=main",
                  f"https://github.com/717998477/plain-core-private.git?branch={core_branch}")
    s = s.replace("https://github.com/plainhub/plain-core.git",
                  f"https://github.com/717998477/plain-core-private.git?branch={core_branch}")
    s = s.replace("https://github.com/717998477/plain-core-private.git?branch=main",
                  f"https://github.com/717998477/plain-core-private.git?branch={core_branch}")
    # dev profile strip
    if 'strip = "symbols"' not in s:
        s = s.replace('[profile.dev]', '[profile.dev]\nstrip = "symbols"', 1)
    if s != orig:
        write(p, s)
    # Cargo.lock 同步替换 git 源，并把锁定的 commit 更新为 plain-core-private 对应分支 HEAD
    lock = P("plain-rs/Cargo.lock")
    if os.path.exists(lock):
        lk = read(lock)
        lk2 = lk.replace("https://github.com/plainhub/plain-core.git?branch=main",
                         f"https://github.com/717998477/plain-core-private.git?branch={core_branch}")
        lk2 = lk2.replace("https://github.com/plainhub/plain-core.git",
                          f"https://github.com/717998477/plain-core-private.git?branch={core_branch}")
        lk2 = lk2.replace(f"https://github.com/717998477/plain-core-private.git?branch=main",
                          f"https://github.com/717998477/plain-core-private.git?branch={core_branch}")
        try:
            import subprocess
            head = subprocess.check_output(
                ["git", "ls-remote", "https://github.com/717998477/plain-core-private.git", core_branch],
                stderr=subprocess.DEVNULL, timeout=60,
            ).decode().split()[0]
            lk2 = re.sub(rf'(plain-core-private\.git\?branch={core_branch}#)[0-9a-f]{{40}}',
                         lambda m: m.group(1) + head, lk2)
            print(f"   Cargo.lock 锁定 plain-core-private@{core_branch}:{head[:12]}")
        except Exception as e:  # noqa
            print(f"   ⚠️ 获取 plain-core-private {core_branch} HEAD 失败: {e}")
        if lk2 != lk:
            write(lock, lk2)
            print("   Cargo.lock git 源已同步")
    if "plain-core-private.git" in s and 'strip = "symbols"' in s:
        record("cargo", True, f"core 指向 private({core_branch}) + dev strip + lock 同步")
        return True
    record("cargo", False, "Cargo 补丁不完整")
    return False

# ---------- 主流程 ----------
def main():
    print(f"== PlainApp 补丁应用 @ {ROOT} ==")
    steps = [
        ("copy-files", copy_new_files),
        ("feature-type", patch_feature_type),
        ("settings-page", patch_settings_page),
        ("settings-card", patch_settings_card),
        ("main-activity", patch_main_activity),
        ("main-app", patch_main_app),
        ("strings", patch_strings),
        ("build-gradle", patch_build_gradle),
        ("debug-manifest", patch_debug_manifest),
        ("leakcanary-file", remove_leakcanary_file),
        ("cargo", patch_cargo),
    ]
    critical_fail = []
    for name, fn in steps:
        try:
            if not fn():
                critical_fail.append(name)
        except Exception as e:  # noqa
            critical_fail.append(name)
            print(f"❌ [{name}] 异常: {e}")
    print("\n== 汇总 ==")
    if critical_fail:
        print(f"❌ 关键补丁失败: {', '.join(critical_fail)}")
        return 1
    print("✅ 全部关键补丁已应用")
    return 0

if __name__ == "__main__":
    sys.exit(main())
