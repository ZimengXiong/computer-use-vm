import AppKit
import ApplicationServices
import CoreGraphics
import Foundation

enum HelperError: Error, CustomStringConvertible {
    case usage(String)
    case screenshotUnavailable
    case pngEncodingFailed
    case invalidNumber(String)
    case unsupportedKey(String)
    case accessibilityUnavailable
    case elementNotFound(Int)

    var description: String {
        switch self {
        case .usage(let text): return text
        case .screenshotUnavailable: return "screenshot unavailable"
        case .pngEncodingFailed: return "png encoding failed"
        case .invalidNumber(let value): return "invalid number: \(value)"
        case .unsupportedKey(let key): return "unsupported key: \(key)"
        case .accessibilityUnavailable: return "accessibility unavailable"
        case .elementNotFound(let id): return "element not found: \(id)"
        }
    }
}

func jsonEscape(_ value: String) -> String {
    let data = try! JSONSerialization.data(withJSONObject: [value], options: [])
    let encoded = String(data: data, encoding: .utf8)!
    return String(encoded.dropFirst(2).dropLast(2))
}

func printJSON(_ pairs: [(String, String)]) {
    let body = pairs.map { "\"\($0.0)\":\($0.1)" }.joined(separator: ",")
    print("{\(body)}")
}

func intArg(_ value: String) throws -> Int {
    guard let number = Int(value) else { throw HelperError.invalidNumber(value) }
    return number
}

func permissions() {
    let axOptions = [kAXTrustedCheckOptionPrompt.takeUnretainedValue() as String: true] as CFDictionary
    let axTrusted = AXIsProcessTrustedWithOptions(axOptions)
    var screenTrusted = true
    if #available(macOS 10.15, *) {
        screenTrusted = CGPreflightScreenCaptureAccess()
        if !screenTrusted {
            screenTrusted = CGRequestScreenCaptureAccess()
        }
    }
    printJSON([
        ("accessibility_trusted", axTrusted ? "true" : "false"),
        ("screen_capture_trusted", screenTrusted ? "true" : "false")
    ])
}

func screenshot() throws {
    let path = NSTemporaryDirectory() + "/computer-use-vm-screenshot-\(UUID().uuidString).png"
    let proc = Process()
    proc.executableURL = URL(fileURLWithPath: "/usr/sbin/screencapture")
    proc.arguments = ["-x", "-t", "png", path]
    try proc.run()
    proc.waitUntilExit()
    guard proc.terminationStatus == 0, FileManager.default.fileExists(atPath: path) else {
        throw HelperError.screenshotUnavailable
    }
    let data = try Data(contentsOf: URL(fileURLWithPath: path))
    let image = NSImage(data: data)
    let size = image?.size ?? .zero
    try? FileManager.default.removeItem(atPath: path)
    let encoded = data.base64EncodedString()
    printJSON([
        ("width", "\(Int(size.width))"),
        ("height", "\(Int(size.height))"),
        ("scale", "1"),
        ("png_base64", "\"\(encoded)\"")
    ])
}

func axString(_ element: AXUIElement, _ attribute: CFString) -> String? {
    var value: CFTypeRef?
    let result = AXUIElementCopyAttributeValue(element, attribute, &value)
    guard result == .success, let value else { return nil }
    if let string = value as? String {
        return string.isEmpty ? nil : string
    }
    if let number = value as? NSNumber {
        return number.stringValue
    }
    return nil
}

func axBool(_ element: AXUIElement, _ attribute: CFString) -> Bool? {
    var value: CFTypeRef?
    let result = AXUIElementCopyAttributeValue(element, attribute, &value)
    guard result == .success, let number = value as? NSNumber else { return nil }
    return number.boolValue
}

func axChildren(_ element: AXUIElement) -> [AXUIElement] {
    var value: CFTypeRef?
    let result = AXUIElementCopyAttributeValue(element, kAXChildrenAttribute as CFString, &value)
    guard result == .success, let children = value as? [AXUIElement] else { return [] }
    return children
}

func axActions(_ element: AXUIElement) -> [String] {
    var names: CFArray?
    let result = AXUIElementCopyActionNames(element, &names)
    guard result == .success, let values = names as? [String] else { return [] }
    return values
}

func axFrame(_ element: AXUIElement) -> [String: Double]? {
    var positionRef: CFTypeRef?
    var sizeRef: CFTypeRef?
    guard AXUIElementCopyAttributeValue(element, kAXPositionAttribute as CFString, &positionRef) == .success,
          AXUIElementCopyAttributeValue(element, kAXSizeAttribute as CFString, &sizeRef) == .success,
          let positionValue = positionRef,
          let sizeValue = sizeRef else {
        return nil
    }
    var point = CGPoint.zero
    var size = CGSize.zero
    guard AXValueGetValue(positionValue as! AXValue, .cgPoint, &point),
          AXValueGetValue(sizeValue as! AXValue, .cgSize, &size) else {
        return nil
    }
    return [
        "x": Double(point.x),
        "y": Double(point.y),
        "width": Double(size.width),
        "height": Double(size.height)
    ]
}

func axNode(_ element: AXUIElement, depth: Int, maxDepth: Int, maxChildren: Int, counter: inout Int) -> [String: Any] {
    counter += 1
    var node: [String: Any] = ["id": counter]
    let stringAttributes: [(String, CFString)] = [
        ("role", kAXRoleAttribute as CFString),
        ("subrole", kAXSubroleAttribute as CFString),
        ("title", kAXTitleAttribute as CFString),
        ("description", kAXDescriptionAttribute as CFString),
        ("value", kAXValueAttribute as CFString),
        ("identifier", kAXIdentifierAttribute as CFString),
        ("help", kAXHelpAttribute as CFString)
    ]
    for (name, attribute) in stringAttributes {
        if let value = axString(element, attribute) {
            node[name] = value
        }
    }
    if let enabled = axBool(element, kAXEnabledAttribute as CFString) {
        node["enabled"] = enabled
    }
    if let focused = axBool(element, kAXFocusedAttribute as CFString) {
        node["focused"] = focused
    }
    if let frame = axFrame(element) {
        node["frame"] = frame
    }
    let actions = axActions(element)
    if !actions.isEmpty {
        node["actions"] = actions
    }
    if depth < maxDepth {
        let children = axChildren(element)
        if !children.isEmpty {
            node["children"] = children.prefix(maxChildren).map { child in
                axNode(child, depth: depth + 1, maxDepth: maxDepth, maxChildren: maxChildren, counter: &counter)
            }
            if children.count > maxChildren {
                node["children_truncated"] = children.count - maxChildren
            }
        }
    }
    return node
}

func axRoots() throws -> (NSRunningApplication, [AXUIElement]) {
    guard AXIsProcessTrusted() else {
        throw HelperError.accessibilityUnavailable
    }
    guard let app = NSWorkspace.shared.frontmostApplication else {
        throw HelperError.accessibilityUnavailable
    }
    let appElement = AXUIElementCreateApplication(app.processIdentifier)
    var windowsRef: CFTypeRef?
    var roots: [AXUIElement] = []
    if AXUIElementCopyAttributeValue(appElement, kAXFocusedWindowAttribute as CFString, &windowsRef) == .success,
       let window = windowsRef {
        roots = [window as! AXUIElement]
    } else if AXUIElementCopyAttributeValue(appElement, kAXWindowsAttribute as CFString, &windowsRef) == .success,
              let windows = windowsRef as? [AXUIElement] {
        roots = windows
    } else {
        roots = [appElement]
    }
    return (app, roots)
}

func axTree(maxDepth: Int, maxChildren: Int) throws {
    let (app, roots) = try axRoots()
    var counter = 0
    let tree = roots.prefix(maxChildren).map { root in
        axNode(root, depth: 0, maxDepth: maxDepth, maxChildren: maxChildren, counter: &counter)
    }
    let payload: [String: Any] = [
        "app": [
            "localized_name": app.localizedName ?? "",
            "bundle_identifier": app.bundleIdentifier ?? "",
            "pid": app.processIdentifier
        ],
        "max_depth": maxDepth,
        "max_children": maxChildren,
        "node_count": counter,
        "tree": tree
    ]
    let data = try JSONSerialization.data(withJSONObject: payload, options: [])
    print(String(data: data, encoding: .utf8)!)
}

func axFind(_ element: AXUIElement, target: Int, depth: Int, maxDepth: Int, maxChildren: Int, counter: inout Int) -> AXUIElement? {
    counter += 1
    if counter == target {
        return element
    }
    if depth >= maxDepth {
        return nil
    }
    for child in axChildren(element).prefix(maxChildren) {
        if let found = axFind(child, target: target, depth: depth + 1, maxDepth: maxDepth, maxChildren: maxChildren, counter: &counter) {
            return found
        }
    }
    return nil
}

func axElement(id: Int, maxDepth: Int, maxChildren: Int) throws -> AXUIElement {
    let (_, roots) = try axRoots()
    var counter = 0
    for root in roots.prefix(maxChildren) {
        if let found = axFind(root, target: id, depth: 0, maxDepth: maxDepth, maxChildren: maxChildren, counter: &counter) {
            return found
        }
    }
    throw HelperError.elementNotFound(id)
}

func axPress(id: Int, maxDepth: Int, maxChildren: Int) throws {
    let element = try axElement(id: id, maxDepth: maxDepth, maxChildren: maxChildren)
    let result = AXUIElementPerformAction(element, kAXPressAction as CFString)
    if result != .success {
        if let frame = axFrame(element) {
            click(x: Int(frame["x"]! + frame["width"]! / 2.0), y: Int(frame["y"]! + frame["height"]! / 2.0), buttonName: "left")
            return
        }
        throw HelperError.accessibilityUnavailable
    }
    printJSON([("ok", "true"), ("action", "\"AXPress\""), ("id", "\(id)")])
}

func axClick(id: Int, maxDepth: Int, maxChildren: Int) throws {
    let element = try axElement(id: id, maxDepth: maxDepth, maxChildren: maxChildren)
    guard let frame = axFrame(element) else {
        throw HelperError.elementNotFound(id)
    }
    click(x: Int(frame["x"]! + frame["width"]! / 2.0), y: Int(frame["y"]! + frame["height"]! / 2.0), buttonName: "left")
}

func axSetValue(id: Int, value: String, maxDepth: Int, maxChildren: Int) throws {
    let element = try axElement(id: id, maxDepth: maxDepth, maxChildren: maxChildren)
    let result = AXUIElementSetAttributeValue(element, kAXValueAttribute as CFString, value as CFTypeRef)
    if result != .success {
        try axClick(id: id, maxDepth: maxDepth, maxChildren: maxChildren)
        try typeText(value)
        return
    }
    printJSON([("ok", "true"), ("action", "\"AXSetValue\""), ("id", "\(id)")])
}

func postMouseMove(x: Int, y: Int) {
    let point = CGPoint(x: x, y: y)
    CGEvent(mouseEventSource: nil, mouseType: .mouseMoved, mouseCursorPosition: point, mouseButton: .left)?.post(tap: .cghidEventTap)
}

func click(x: Int, y: Int, buttonName: String) {
    let point = CGPoint(x: x, y: y)
    let button: CGMouseButton = buttonName == "right" ? .right : (buttonName == "middle" ? .center : .left)
    let downType: CGEventType = button == .right ? .rightMouseDown : (button == .center ? .otherMouseDown : .leftMouseDown)
    let upType: CGEventType = button == .right ? .rightMouseUp : (button == .center ? .otherMouseUp : .leftMouseUp)
    postMouseMove(x: x, y: y)
    usleep(20_000)
    CGEvent(mouseEventSource: nil, mouseType: downType, mouseCursorPosition: point, mouseButton: button)?.post(tap: .cghidEventTap)
    usleep(30_000)
    CGEvent(mouseEventSource: nil, mouseType: upType, mouseCursorPosition: point, mouseButton: button)?.post(tap: .cghidEventTap)
    printJSON([("ok", "true")])
}

func keyCode(_ key: String) throws -> CGKeyCode {
    let table: [String: CGKeyCode] = [
        "a": 0, "s": 1, "d": 2, "f": 3, "h": 4, "g": 5, "z": 6, "x": 7, "c": 8, "v": 9,
        "b": 11, "q": 12, "w": 13, "e": 14, "r": 15, "y": 16, "t": 17, "1": 18, "2": 19,
        "3": 20, "4": 21, "6": 22, "5": 23, "=": 24, "9": 25, "7": 26, "-": 27, "8": 28,
        "0": 29, "]": 30, "o": 31, "u": 32, "[": 33, "i": 34, "p": 35, "return": 36,
        "enter": 36, "l": 37, "j": 38, "'": 39, "k": 40, ";": 41, "\\": 42, ",": 43, "/": 44,
        "n": 45, "m": 46, ".": 47, "tab": 48, "space": 49, "`": 50, "delete": 51, "escape": 53,
        "esc": 53, "command": 55, "shift": 56, "capslock": 57, "option": 58, "control": 59,
        "rightshift": 60, "rightoption": 61, "rightcontrol": 62, "fn": 63, "f17": 64, "volumeup": 72,
        "volumedown": 73, "mute": 74, "f18": 79, "f19": 80, "f20": 90, "f5": 96, "f6": 97,
        "f7": 98, "f3": 99, "f8": 100, "f9": 101, "f11": 103, "f13": 105, "f16": 106,
        "f14": 107, "f10": 109, "f12": 111, "f15": 113, "help": 114, "home": 115, "pageup": 116,
        "forwarddelete": 117, "f4": 118, "end": 119, "f2": 120, "pagedown": 121, "f1": 122,
        "left": 123, "right": 124, "down": 125, "up": 126
    ]
    let normalized = key.lowercased()
    guard let code = table[normalized] else { throw HelperError.unsupportedKey(key) }
    return code
}

func flags(_ modifiers: [String]) -> CGEventFlags {
    var result = CGEventFlags()
    for modifier in modifiers.map({ $0.lowercased() }) {
        switch modifier {
        case "cmd", "command": result.insert(.maskCommand)
        case "shift": result.insert(.maskShift)
        case "option", "alt": result.insert(.maskAlternate)
        case "control", "ctrl": result.insert(.maskControl)
        default: break
        }
    }
    return result
}

func pressKey(_ key: String, modifiers: [String]) throws {
    let code = try keyCode(key)
    let eventFlags = flags(modifiers)
    let down = CGEvent(keyboardEventSource: nil, virtualKey: code, keyDown: true)
    down?.flags = eventFlags
    down?.post(tap: .cghidEventTap)
    usleep(20_000)
    let up = CGEvent(keyboardEventSource: nil, virtualKey: code, keyDown: false)
    up?.flags = eventFlags
    up?.post(tap: .cghidEventTap)
    printJSON([("ok", "true")])
}

func typeText(_ text: String) throws {
    let pasteboard = NSPasteboard.general
    pasteboard.clearContents()
    pasteboard.setString(text, forType: .string)
    try pressKey("v", modifiers: ["command"])
}

func main() throws {
    var args = CommandLine.arguments
    _ = args.removeFirst()
    guard let command = args.first else {
        throw HelperError.usage("usage: computer-use-vm-guest-helper permissions|screenshot|ax-tree [depth] [max-children]|ax-press ID [depth] [max-children]|ax-click ID [depth] [max-children]|ax-set-value ID VALUE [depth] [max-children]|click X Y [button]|type TEXT|key KEY [modifiers...]")
    }
    args.removeFirst()
    switch command {
    case "permissions":
        permissions()
    case "screenshot":
        try screenshot()
    case "ax-tree":
        let depth = args.count >= 1 ? try intArg(args[0]) : 5
        let maxChildren = args.count >= 2 ? try intArg(args[1]) : 80
        try axTree(maxDepth: max(1, depth), maxChildren: max(1, maxChildren))
    case "ax-press":
        guard args.count >= 1 else { throw HelperError.usage("ax-press requires ID [depth] [max-children]") }
        let depth = args.count >= 2 ? try intArg(args[1]) : 5
        let maxChildren = args.count >= 3 ? try intArg(args[2]) : 80
        try axPress(id: try intArg(args[0]), maxDepth: max(1, depth), maxChildren: max(1, maxChildren))
    case "ax-click":
        guard args.count >= 1 else { throw HelperError.usage("ax-click requires ID [depth] [max-children]") }
        let depth = args.count >= 2 ? try intArg(args[1]) : 5
        let maxChildren = args.count >= 3 ? try intArg(args[2]) : 80
        try axClick(id: try intArg(args[0]), maxDepth: max(1, depth), maxChildren: max(1, maxChildren))
    case "ax-set-value":
        guard args.count >= 2 else { throw HelperError.usage("ax-set-value requires ID VALUE [depth] [max-children]") }
        let depth = args.count >= 3 ? try intArg(args[2]) : 5
        let maxChildren = args.count >= 4 ? try intArg(args[3]) : 80
        try axSetValue(id: try intArg(args[0]), value: args[1], maxDepth: max(1, depth), maxChildren: max(1, maxChildren))
    case "click":
        guard args.count >= 2 else { throw HelperError.usage("click requires X Y [button]") }
        click(x: try intArg(args[0]), y: try intArg(args[1]), buttonName: args.count >= 3 ? args[2] : "left")
    case "type":
        guard let text = args.first else { throw HelperError.usage("type requires TEXT") }
        try typeText(text)
    case "key":
        guard let key = args.first else { throw HelperError.usage("key requires KEY [modifiers...]") }
        try pressKey(key, modifiers: Array(args.dropFirst()))
    default:
        throw HelperError.usage("unknown command: \(command)")
    }
}

do {
    try main()
} catch {
    fputs("{\"error\":\"\(jsonEscape(String(describing: error)))\"}\n", stderr)
    exit(1)
}
