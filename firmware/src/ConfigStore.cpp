#include "ConfigStore.h"
#include <Preferences.h>

namespace {
  constexpr char NS[]  = "raroto";
  constexpr char KEY[] = "settings";
  Preferences prefs;
}

void ConfigStore::load(Settings& out) {
  Settings defaults;                     // constructor holds the defaults
  prefs.begin(NS, /*readOnly=*/true);
  const size_t got = prefs.getBytesLength(KEY);
  if (got == sizeof(Settings)) {
    Settings tmp;
    prefs.getBytes(KEY, &tmp, sizeof(Settings));
    if (tmp.version == defaults.version) {
      out = tmp;
      prefs.end();
      return;
    }
  }
  prefs.end();
  out = defaults;                        // first boot or version bump -> defaults
}

bool ConfigStore::save(const Settings& s) {
  prefs.begin(NS, /*readOnly=*/false);
  const size_t n = prefs.putBytes(KEY, &s, sizeof(Settings));
  prefs.end();
  return n == sizeof(Settings);
}

void ConfigStore::factoryReset() {
  prefs.begin(NS, /*readOnly=*/false);
  prefs.clear();
  prefs.end();
}
