// Injected (DYLD_INSERT_LIBRARIES) into the background agent Chrome for Testing:
// it can never make itself the front app or auto-activate on launch, so the
// user's work is never interrupted. Built on first use by browser_window.py.
#import <AppKit/AppKit.h>
#import <objc/runtime.h>
static void noop(id self, SEL _cmd, ...) {}
static BOOL no(id self, SEL _cmd, ...) { return NO; }
static IMP orig_policy;
static BOOL accessory(id self, SEL _cmd, NSApplicationActivationPolicy p) {
  return ((BOOL (*)(id, SEL, NSApplicationActivationPolicy))orig_policy)(self, _cmd, NSApplicationActivationPolicyAccessory);
}
static void stub(Class c, SEL s, IMP imp) {
  Method m = class_getInstanceMethod(c, s);
  if (m) method_setImplementation(m, imp);
}
__attribute__((constructor)) static void init(void) {
  Class app = NSClassFromString(@"NSApplication");
  if (!app) return;  // helper processes without AppKit
  stub(app, @selector(activateIgnoringOtherApps:), (IMP)noop);
  stub(app, @selector(activate), (IMP)noop);
  stub(app, @selector(unhide:), (IMP)noop);
  stub(NSClassFromString(@"NSRunningApplication"), @selector(activateWithOptions:), (IMP)no);
  Method m = class_getInstanceMethod(app, @selector(setActivationPolicy:));
  orig_policy = method_setImplementation(m, (IMP)accessory);
}
