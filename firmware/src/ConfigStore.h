// ConfigStore.h — persist Settings to NVS (Preferences) as a versioned blob.
#pragma once
#include "ControlTypes.h"

namespace ConfigStore {
  void load(Settings& out);      // fills defaults if none/mismatched version
  bool save(const Settings& s);
  void factoryReset();
}
