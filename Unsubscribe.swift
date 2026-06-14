// Unsubscribe — a macOS menu bar app that drives unsubscribe.py.
// Lives in the top menu bar (no Dock icon) and offers controls to run it,
// preview a dry run, open the log / captured spammer list, toggle the daily
// schedule, and toggle launch-at-login.
//
// Built by build-app.command via: swiftc Unsubscribe.swift -o <app>/MacOS/Unsubscribe
import Cocoa
import ServiceManagement

let RESOURCES = Bundle.main.resourcePath ?? "."
let SCRIPT = RESOURCES + "/unsubscribe.py"
let STATE = NSString(string: "~/Library/Application Support/Unsubscribe").expandingTildeInPath
let LABEL = "com.local.unsubscribe"
let PLIST = NSString(string: "~/Library/LaunchAgents/\(LABEL).plist").expandingTildeInPath
let REPO_URL = "https://github.com/henrybasset/unsubscribe"

func pythonPath() -> String {
    let candidates = ["__PY__", "/opt/homebrew/bin/python3",
                      "/usr/local/bin/python3", "/usr/bin/python3"]
    for c in candidates where FileManager.default.isExecutableFile(atPath: c) {
        return c
    }
    return "/usr/bin/python3"
}

@discardableResult
func run(_ tool: String, _ args: [String]) -> (status: Int32, out: String) {
    let p = Process()
    p.executableURL = URL(fileURLWithPath: tool)
    p.arguments = args
    let pipe = Pipe()
    p.standardOutput = pipe
    p.standardError = pipe
    do { try p.run() } catch { return (-1, "\(error)") }
    let data = pipe.fileHandleForReading.readDataToEndOfFile()
    p.waitUntilExit()
    return (p.terminationStatus, String(data: data, encoding: .utf8) ?? "")
}

func openPath(_ path: String) {
    if !FileManager.default.fileExists(atPath: path) {
        try? "".write(toFile: path, atomically: true, encoding: .utf8)
    }
    NSWorkspace.shared.open(URL(fileURLWithPath: path))
}

final class AppDelegate: NSObject, NSApplicationDelegate {
    var statusItem: NSStatusItem!
    let lastRunItem = NSMenuItem(title: "Last run: never", action: nil, keyEquivalent: "")
    let scheduleItem = NSMenuItem(title: "Run Daily at 9:00 AM",
                                  action: #selector(toggleSchedule), keyEquivalent: "")
    let loginItem = NSMenuItem(title: "Open at Login",
                               action: #selector(toggleLogin), keyEquivalent: "")
    var busy = false

    func applicationDidFinishLaunching(_ note: Notification) {
        NSApp.setActivationPolicy(.accessory)
        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        if let btn = statusItem.button {
            let img = NSImage(systemSymbolName: "envelope.badge",
                              accessibilityDescription: "Unsubscribe")
            img?.isTemplate = true
            btn.image = img
        }
        buildMenu()
        refreshStates()
    }

    func add(_ menu: NSMenu, _ title: String, _ sel: Selector?, _ key: String = "") -> NSMenuItem {
        let item = NSMenuItem(title: title, action: sel, keyEquivalent: key)
        item.target = self
        menu.addItem(item)
        return item
    }

    func buildMenu() {
        let menu = NSMenu()
        let header = NSMenuItem(title: "Unsubscribe!", action: nil, keyEquivalent: "")
        header.isEnabled = false
        menu.addItem(header)
        menu.addItem(.separator())
        _ = add(menu, "Unsubscribe Now", #selector(runNow), "u")
        _ = add(menu, "Preview (Dry Run)…", #selector(runDry), "d")
        _ = add(menu, "Move No-Link Spam to Trash", #selector(deleteJunk))
        menu.addItem(.separator())
        _ = add(menu, "Gmail: Unsubscribe from Spam", #selector(gmailNow), "g")
        _ = add(menu, "Gmail: Preview (Dry Run)…", #selector(gmailDry))
        menu.addItem(.separator())
        _ = add(menu, "Triage Inbox for Actions (AI)", #selector(triageNow), "t")
        _ = add(menu, "Preview Triage (Dry Run)…", #selector(triageDry))
        menu.addItem(.separator())
        lastRunItem.isEnabled = false
        menu.addItem(lastRunItem)
        _ = add(menu, "Open Log…", #selector(openLog))
        _ = add(menu, "Open Spammer List…", #selector(openSpammers))
        menu.addItem(.separator())
        scheduleItem.target = self
        menu.addItem(scheduleItem)
        loginItem.target = self
        menu.addItem(loginItem)
        menu.addItem(.separator())
        _ = add(menu, "View on GitHub…", #selector(openGitHub))
        let quit = NSMenuItem(title: "Quit Unsubscribe",
                              action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        quit.target = NSApp
        menu.addItem(quit)
        statusItem.menu = menu
    }

    func refreshStates() {
        let loaded = run("/bin/launchctl", ["list", LABEL]).status == 0
        scheduleItem.state = loaded ? .on : .off
        if #available(macOS 13.0, *) {
            loginItem.state = (SMAppService.mainApp.status == .enabled) ? .on : .off
        } else {
            loginItem.isHidden = true
        }
    }

    // MARK: - Running the script

    func execute(title: String, script: String, dryRun: Bool, extra: [String] = []) {
        if busy { return }
        busy = true
        lastRunItem.title = "Running \(title)…"
        let py = pythonPath()
        var args = [RESOURCES + "/" + script]
        if dryRun { args.append("--dry-run") }
        args += extra
        DispatchQueue.global().async {
            let result = run(py, args)
            DispatchQueue.main.async {
                self.busy = false
                self.lastRunItem.title = "Last run: \(title)\(dryRun ? " (preview)" : "")"
                self.showResult(title: title, out: result.out, dryRun: dryRun)
            }
        }
    }

    func showResult(title: String, out: String, dryRun: Bool) {
        let tail = out.split(separator: "\n").suffix(10).joined(separator: "\n")
        NSApp.activate(ignoringOtherApps: true)
        let a = NSAlert()
        a.messageText = dryRun ? "\(title) — Preview" : "\(title) — Done"
        a.informativeText = tail.isEmpty ? "No output." : tail
        a.addButton(withTitle: "OK")
        a.runModal()
    }

    @objc func runNow() { execute(title: "Unsubscribe", script: "unsubscribe.py", dryRun: false) }
    @objc func runDry() { execute(title: "Unsubscribe", script: "unsubscribe.py", dryRun: true) }
    @objc func triageNow() { execute(title: "Triage", script: "triage.py", dryRun: false) }
    @objc func triageDry() { execute(title: "Triage", script: "triage.py", dryRun: true) }
    @objc func gmailNow() { execute(title: "Gmail Unsubscribe", script: "gmail_unsubscribe.py", dryRun: false) }
    @objc func gmailDry() { execute(title: "Gmail Unsubscribe", script: "gmail_unsubscribe.py", dryRun: true) }

    @objc func deleteJunk() {
        NSApp.activate(ignoringOtherApps: true)
        let a = NSAlert()
        a.messageText = "Move no-link spam to Trash?"
        a.informativeText = "This unsubscribes as usual, and also moves junk that has "
            + "no unsubscribe link to Trash (recoverable). Continue?"
        a.addButton(withTitle: "Move to Trash")
        a.addButton(withTitle: "Cancel")
        if a.runModal() == .alertFirstButtonReturn {
            execute(title: "Delete Spam", script: "unsubscribe.py", dryRun: false, extra: ["--delete"])
        }
    }
    @objc func openLog() { openPath(STATE + "/log.txt") }
    @objc func openSpammers() { openPath(STATE + "/spammers.csv") }
    @objc func openGitHub() { NSWorkspace.shared.open(URL(string: REPO_URL)!) }

    // MARK: - Schedule toggle (launchd)

    @objc func toggleSchedule() {
        let loaded = run("/bin/launchctl", ["list", LABEL]).status == 0
        if loaded {
            run("/bin/launchctl", ["unload", PLIST])
            try? FileManager.default.removeItem(atPath: PLIST)
        } else {
            writePlist()
            run("/bin/launchctl", ["load", PLIST])
        }
        refreshStates()
    }

    func writePlist() {
        try? FileManager.default.createDirectory(
            atPath: STATE, withIntermediateDirectories: true)
        let py = pythonPath()
        let plist = """
        <?xml version="1.0" encoding="UTF-8"?>
        <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
        <plist version="1.0">
        <dict>
          <key>Label</key><string>\(LABEL)</string>
          <key>ProgramArguments</key>
          <array><string>\(py)</string><string>\(SCRIPT)</string></array>
          <key>StartCalendarInterval</key>
          <dict><key>Hour</key><integer>9</integer><key>Minute</key><integer>0</integer></dict>
          <key>StandardOutPath</key><string>\(STATE)/launchd.log</string>
          <key>StandardErrorPath</key><string>\(STATE)/launchd.log</string>
        </dict>
        </plist>
        """
        let dir = (PLIST as NSString).deletingLastPathComponent
        try? FileManager.default.createDirectory(atPath: dir, withIntermediateDirectories: true)
        try? plist.write(toFile: PLIST, atomically: true, encoding: .utf8)
    }

    // MARK: - Login item

    @objc func toggleLogin() {
        guard #available(macOS 13.0, *) else { return }
        do {
            if SMAppService.mainApp.status == .enabled {
                try SMAppService.mainApp.unregister()
            } else {
                try SMAppService.mainApp.register()
            }
        } catch {
            NSApp.activate(ignoringOtherApps: true)
            let a = NSAlert()
            a.messageText = "Could not change login setting"
            a.informativeText = "\(error.localizedDescription)"
            a.runModal()
        }
        refreshStates()
    }
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.run()
