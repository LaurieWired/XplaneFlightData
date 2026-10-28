// VNAV Calculator for X-Plane MFD
// JSF AV C++ Coding Standard Compliant Version
//
// Calculates vertical navigation parameters:
// - Top of Descent (TOD) distance
// - Required vertical speed for path
// - Flight path angle
// - Time to altitude constraint

#include "xplane_mfd_calc.h"
#include <cmath>
#include <cstdint>
#include <iomanip>
#include <iostream>

namespace airv
{
namespace calc
{
// Mathematical constants
constexpr double three_deg_rad = 3.0 * units::deg_to_rad;

// Calculation constants
constexpr double vs_conversion_factor = 101.27;  // Converts GS*tan(gamma) to VS in fpm
constexpr double min_distance_nm      = 0.01;
constexpr double min_groundspeed_kts  = 1.0;
constexpr double min_vs_for_time_calc = 1.0;
constexpr double infinite_time        = 999.9;
constexpr double zero_distance        = 0.0;
constexpr double thousand_feet        = 1000.0;

struct VNAVData
{
    double altitude_to_lose_ft;     // Altitude change required
    double flight_path_angle_deg;   // Flight path angle (negative = descent)
    double required_vs_fpm;         // Required vertical speed
    double tod_distance_nm;         // Top of descent distance (for 3 deg path)
    double time_to_constraint_min;  // Time to reach altitude at current VS
    double distance_per_1000ft;     // Distance traveled per 1000 ft altitude change
    double vs_for_3deg;             // Vertical speed required for 3 deg path
    bool is_descent;                // True if descending, false if climbing
};

// Calculate VNAV parameters
VNAVData calculate_vnav(double current_alt_ft,   // Current altitude (feet)
                        double target_alt_ft,    // Target altitude (feet)
                        double distance_nm,      // Distance to constraint (nautical miles)
                        double groundspeed_kts,  // Groundspeed (knots)
                        double current_vs_fpm)   // Current vertical speed (feet per minute)
{
    VNAVData result;

    // Calculate altitude change (positive = climb, negative = descend)
    double altitude_change_ft  = target_alt_ft - current_alt_ft;
    result.altitude_to_lose_ft = -altitude_change_ft;  // Legacy field name
    result.is_descent          = altitude_change_ft < zero_distance;

    // Avoid division by zero
    if (distance_nm < min_distance_nm)
        distance_nm = min_distance_nm;
    if (groundspeed_kts < min_groundspeed_kts)
        groundspeed_kts = min_groundspeed_kts;

    // Calculate flight path angle (positive = climb, negative = descent)
    double distance_ft           = distance_nm * units::nm_to_ft;
    double gamma_rad             = atan(altitude_change_ft / distance_ft);
    result.flight_path_angle_deg = gamma_rad * units::rad_to_deg;

    // Required vertical speed to meet constraint
    // VS = 101.27 * GS * tan(gamma)
    result.required_vs_fpm = vs_conversion_factor * groundspeed_kts * tan(gamma_rad);

    // Calculate TOD for standard 3 deg descent path
    // D = h / (6076 * tan(3 deg)) or simplified: h / 319
    double abs_alt_change  = fabs(altitude_change_ft);
    result.tod_distance_nm = abs_alt_change / (units::nm_to_ft * tan(three_deg_rad));

    // Vertical speed for 3 deg descent: VS is almost 5 * GS (rule of thumb)
    // More precisely: VS = 101.27 * GS * tan(3 deg) is almost 5.3 * GS
    result.vs_for_3deg = vs_conversion_factor * groundspeed_kts * tan(three_deg_rad);
    if (!result.is_descent)
    {
        result.vs_for_3deg = -result.vs_for_3deg;  // Make positive for climb
    }

    // Time to reach constraint at current vertical speed
    if (fabs(current_vs_fpm) > min_vs_for_time_calc)
    {
        result.time_to_constraint_min = altitude_change_ft / current_vs_fpm;
    }
    else
    {
        result.time_to_constraint_min = infinite_time;
    }

    // Distance per 1000 ft of altitude change
    if (abs_alt_change > min_vs_for_time_calc)
    {
        result.distance_per_1000ft = (distance_nm * thousand_feet) / abs_alt_change;
    }
    else
    {
        result.distance_per_1000ft = zero_distance;
    }

    return result;
}

// Output results as JSON
void print_json(const VNAVData& vnav)
{
    std::cout << std::fixed << std::setprecision(2);
    std::cout << "{\n";
    std::cout << "  \"altitude_to_lose_ft\": " << vnav.altitude_to_lose_ft << ",\n";
    std::cout << "  \"flight_path_angle_deg\": " << vnav.flight_path_angle_deg << ",\n";
    std::cout << "  \"required_vs_fpm\": " << vnav.required_vs_fpm << ",\n";
    std::cout << "  \"tod_distance_nm\": " << vnav.tod_distance_nm << ",\n";
    std::cout << "  \"time_to_constraint_min\": " << vnav.time_to_constraint_min << ",\n";
    std::cout << "  \"distance_per_1000ft\": " << vnav.distance_per_1000ft << ",\n";
    std::cout << "  \"vs_for_3deg\": " << vnav.vs_for_3deg << ",\n";
    std::cout << "  \"is_descent\": " << (vnav.is_descent ? "true" : "false") << "\n";
    std::cout << "}\n";
}

}  // namespace calc
}  // namespace airv

void print_usage(const char* program_name)
{
    std::cerr << "Usage: " << program_name
              << " <current_alt_ft> <target_alt_ft> <distance_nm> <groundspeed_kts> <current_vs_fpm>\n\n";
    std::cerr << "Arguments:\n";
    std::cerr << "  current_alt_ft  : Current altitude (feet)\n";
    std::cerr << "  target_alt_ft   : Target altitude (feet)\n";
    std::cerr << "  distance_nm     : Distance to constraint (nautical miles)\n";
    std::cerr << "  groundspeed_kts : Groundspeed (knots)\n";
    std::cerr << "  current_vs_fpm  : Current vertical speed (feet per minute)\n\n";
    std::cerr << "Example:\n";
    std::cerr << "  " << program_name << " 35000 10000 100 450 -1500\n";
    std::cerr << "  (FL350 to 10000 ft, 100 NM, 450 kts GS, -1500 fpm)\n";
}

int main(int argc,
         char* argv[])
{
    if (argc != 6)
    {
        print_usage(argv[0]);
        return static_cast<int>(airv::Return_code::invalid_argc);
    }

    // Parse arguments
    double current_alt_ft;   // Current altitude (feet)
    double target_alt_ft;    // Target altitude (feet)
    double distance_nm;      // Distance to constraint (nautical miles)
    double groundspeed_kts;  // Groundspeed (knots)
    double current_vs_fpm;   // Current vertical speed (feet per minute)

    if (!airv::utils::parse_double(argv[1], current_alt_ft))
    {
        std::cerr << "Error: Invalid current altitude\n";
        return static_cast<int>(airv::Return_code::parse_failed);
    }
    if (!airv::utils::parse_double(argv[2], target_alt_ft))
    {
        std::cerr << "Error: Invalid target altitude\n";
        return static_cast<int>(airv::Return_code::parse_failed);
    }
    if (!airv::utils::parse_double(argv[3], distance_nm))
    {
        std::cerr << "Error: Invalid distance\n";
        return static_cast<int>(airv::Return_code::parse_failed);
    }
    if (!airv::utils::parse_double(argv[4], groundspeed_kts))
    {
        std::cerr << "Error: Invalid groundspeed\n";
        return static_cast<int>(airv::Return_code::parse_failed);
    }
    if (!airv::utils::parse_double(argv[5], current_vs_fpm))
    {
        std::cerr << "Error: Invalid vertical speed\n";
        return static_cast<int>(airv::Return_code::parse_failed);
    }

    // Calculate and output results
    airv::calc::print_json(
        airv::calc::calculate_vnav(current_alt_ft, target_alt_ft, distance_nm, groundspeed_kts, current_vs_fpm));

    return static_cast<int>(airv::Return_code::success);
}