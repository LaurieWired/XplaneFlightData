// Wind Calculator for X-Plane MFD
// JSF AV C++ Coding Standard Compliant Version
//
// Calculates wind parameters from aircraft position and wind data:
// - headwind
// - crosswind
// - wind correction angle

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
constexpr double wind_calm_threshold = 0.0;

struct WindComponents
{
    double headwind;    // Positive = headwind, negative = tailwind
    double crosswind;   // Positive = from right, negative = from left
    double total_wind;  // Total wind speed
    double wca;         // Wind correction angle
    double drift;       // Drift angle (track - heading)
};

// Normalize angle to 0-360 range
double normalize_angle(double angle)
{
    double result = fmod(angle, units::angle_wrap);
    if (result < wind_calm_threshold)
    {
        result += units::angle_wrap;
    }
    return result;
}

// Calculate wind components relative to aircraft track
WindComponents calculate_wind(double track,       // Ground track (degrees true)
                              double heading,     // Aircraft heading (degrees)
                              double wind_dir,    // Wind direction FROM (degrees)
                              double wind_speed)  // Wind speed (knots)
{
    WindComponents result;

    // Normalize all angles
    track    = normalize_angle(track);
    heading  = normalize_angle(heading);
    wind_dir = normalize_angle(wind_dir);

    // Calculate drift angle
    result.drift = normalize_angle(track - heading);
    if (result.drift > units::half_circle)
        result.drift -= units::angle_wrap;

    // Wind direction is where wind comes FROM
    // Calculate angle of wind-from relative to track
    double wind_from_relative = normalize_angle(wind_dir - track);
    if (wind_from_relative > units::half_circle)
        wind_from_relative -= units::angle_wrap;

    // Convert to radians for trig
    double wind_from_rad = wind_from_relative * units::deg_to_rad;

    // Calculate components using wind-from angle
    result.headwind   = -wind_speed * cos(wind_from_rad);
    result.crosswind  = wind_speed * sin(wind_from_rad);
    result.total_wind = wind_speed;

    // Wind correction angle placeholder
    result.wca = wind_calm_threshold;  // Cannot calculate without TAS

    return result;
}

// Output results as JSON
void print_json(const WindComponents& wind)
{
    std::cout << std::fixed << std::setprecision(2);
    std::cout << "{\n";
    std::cout << "  \"headwind\": " << wind.headwind << ",\n";
    std::cout << "  \"crosswind\": " << wind.crosswind << ",\n";
    std::cout << "  \"total_wind\": " << wind.total_wind << ",\n";
    std::cout << "  \"wca\": " << wind.wca << ",\n";
    std::cout << "  \"drift\": " << wind.drift << "\n";
    std::cout << "}\n";
}

}  // namespace calc
}  // namespace airv

void print_usage(const char* program_name)
{
    std::cerr << "Usage: " << program_name << " <track> <heading> <wind_dir> <wind_speed>\n\n";
    std::cerr << "Arguments:\n";
    std::cerr << "  track      : Ground track (degrees true)\n";
    std::cerr << "  heading    : Aircraft heading (degrees)\n";
    std::cerr << "  wind_dir   : Wind direction FROM (degrees)\n";
    std::cerr << "  wind_speed : Wind speed (knots)\n\n";
    std::cerr << "Example:\n";
    std::cerr << "  " << program_name << " 90 85 270 15\n";
    std::cerr << "  (Track 90°, Heading 85°, Wind from 270° at 15 knots)\n";
}

int main(int argc,
         char* argv[])
{
    if (argc != 5)
    {
        print_usage(argv[0]);
        return static_cast<int>(airv::Return_code::invalid_argc);
    }

    // Parse arguments
    double track;       // Ground track (degrees true)
    double heading;     // Aircraft heading (degrees)
    double wind_dir;    // Wind direction FROM (degrees)
    double wind_speed;  // Wind speed (knots)

    if (!airv::utils::parse_double(argv[1], track))
    {
        std::cerr << "Error: Invalid track angle\n";
        return static_cast<int>(airv::Return_code::parse_failed);
    }
    if (!airv::utils::parse_double(argv[2], heading))
    {
        std::cerr << "Error: Invalid heading\n";
        return static_cast<int>(airv::Return_code::parse_failed);
    }
    if (!airv::utils::parse_double(argv[3], wind_dir))
    {
        std::cerr << "Error: Invalid wind direction\n";
        return static_cast<int>(airv::Return_code::parse_failed);
    }
    if (!airv::utils::parse_double(argv[4], wind_speed))
    {
        std::cerr << "Error: Invalid wind speed\n";
        return static_cast<int>(airv::Return_code::parse_failed);
    }
    if (wind_speed < airv::calc::wind_calm_threshold)
    {
        std::cerr << "Error: Wind speed cannot be negative\n";
        return static_cast<int>(airv::Return_code::invalid_value);
    }

    // Calculate and output results
    airv::calc::print_json(airv::calc::calculate_wind(track, heading, wind_dir, wind_speed));

    return static_cast<int>(airv::Return_code::success);
}