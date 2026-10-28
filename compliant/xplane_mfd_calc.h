#ifndef XPLANE_MFD_CALC
#define XPLANE_MFD_CALC

#include <cstdint>
#include <cstdlib>

namespace airv
{

namespace units
{

// Global mathematical constants
constexpr double pi          = 3.141592653589793;
constexpr double deg_to_rad  = pi / 180.0;
constexpr double rad_to_deg  = 180.0 / pi;
constexpr double gravity     = 9.80665;  // m/pow(s, 2)
constexpr double kts_to_ms   = 0.514444;
constexpr double ft_to_m     = 0.3048;
constexpr double m_to_ft     = 3.28084;
constexpr double nm_to_ft    = 6076.12;
constexpr double angle_wrap  = 360.0;
constexpr double half_circle = 180.0;

}  // namespace units

enum class Return_code : int32_t
{
    success       = 0,  // Code ran successfully
    invalid_argc  = 1,  // Not enough or too much args
    parse_failed  = 2,  // An argument might be a letter instead of a number
    invalid_value = 3,  // An argument is outside the acceptable range
    simulated     = 4,  // Error was forced by the force_error parameter
};

namespace utils
{

// Converts a string to a double
bool parse_double(const char* str,  // Input string
                  double& result)   // Converted double
{
    char* end = nullptr;
    result    = strtod(str, &end);
    return (end != str && *end == '\0');
}

// Converts a string to an int
bool parse_int32(const char* str,  // Input string
                 int32_t& result)  // Converted int
{
    char* end  = nullptr;
    long value = strtol(str, &end, 10);
    if (end != str && *end == '\0')
    {
        result = static_cast<int32_t>(value);
        return true;
    }
    return false;
}

}  // namespace utils

}  // namespace airv

#endif  // !XPLANE_MFD_CALC