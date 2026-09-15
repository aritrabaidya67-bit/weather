/* Host-side translation unit that compiles the real sketch for static checks.
 *
 * It provides the global objects the Arduino core would normally define and
 * then includes the sketch verbatim, so what is compiled here is literally
 * `environmental_monitor.ino` - not a copy that could drift from it. */
#include "stubs.hpp"

HostSerial Serial;
HostWiFi WiFi;
HostWire Wire;

#include "../environmental_monitor/environmental_monitor.ino"

/* The sketch defines setup()/loop(); providing a host main() lets the compiler
 * also report unused-function/unused-variable diagnostics. */
int main() {
  setup();
  return 0;
}
