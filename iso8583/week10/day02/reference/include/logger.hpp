#pragma once

#include <string>

namespace course {

// Write one complete diagnostic line, even if several workers log at once.
// Never log raw payment messages here.
void log(const std::string& message);

} // namespace course
