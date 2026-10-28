// Density Altitude Calculator for X-Plane MFD
// JSF AV C++ Coding Standard Compliant Version
//
// Calculates density altitude and related atmospheric parameters:
// - Density altitude (how "high" the aircraft performs)
// - Pressure altitude
// - True vs Equivalent airspeed conversions
// - Air density ratio (sigma)
// - Performance degradation percentage

#include "xplane_mfd_calc.h"
#include <cmath>
#include <cstdint>
#include <cstring>
#include <iomanip>
#include <iostream>

namespace airv
{
namespace calc
{

constexpr double sea_level_temp_c           = 15.0;
constexpr double temp_lapse_rate            = 0.0019812;  // Celsius per foot (standard lapse rate)
constexpr double kelvin_offset              = 273.15;
constexpr double density_alt_factor         = 120.0;
constexpr double pressure_altitude_constant = 6.8756e-6;
constexpr double pressure_altitude_exponent = 5.2559;
constexpr double min_ias_for_ratio          = 10.0;

// Validation ranges: warning if input is not in range
constexpr double min_altitude_ft   = -2000.0;
constexpr double max_altitude_ft   = 60000.0;
constexpr double min_temperature_c = -60.0;
constexpr double max_temperature_c = 60.0;

struct DensityAltitudeData
{
    double density_altitude_ft;      // Density altitude
    double pressure_altitude_ft;     // Pressure altitude (from setting)
    double air_density_ratio;        // ratio to sea level (sigma)
    double temperature_deviation_c;  // Deviation from ISA
    double performance_loss_pct;     // % performance loss vs sea level
    double eas_kts;                  // Equivalent airspeed
    double tas_to_ias_ratio;         // TAS/IAS ratio
    double pressure_ratio;           // Pressure ratio vs sea level
};

// Calculate ISA temperature at given pressure altitude
double isa_temperature_c(double pressure_altitude_ft)  // Pressure altitude (feet)
{
    return sea_level_temp_c - (temp_lapse_rate * pressure_altitude_ft);
}

// Calculate density altitude using exact formula
// DA = PA + [120 * (OAT - ISA)]
double calculate_density_altitude(double pressure_altitude_ft,  // Pressure altitude (feet)
                                  double oat_celsius)           // Outside air temperature (Celsius)
{
    // ISA temperature at pressure altitude
    double isa_temp = isa_temperature_c(pressure_altitude_ft);

    // Temperature deviation from ISA
    double temp_deviation = oat_celsius - isa_temp;

    // Density altitude approximation (good to about 1% accuracy)
    double density_altitude = pressure_altitude_ft + (density_alt_factor * temp_deviation);

    return density_altitude;
}

// Calculate air density ratio (sigma)
// sigma = rho / rho<sub>0</sub>
double calculate_density_ratio(double pressure_altitude_ft,
                               double oat_celsius)
{
    // Convert to absolute temperature
    double temp_k           = oat_celsius + kelvin_offset;
    double sea_level_temp_k = sea_level_temp_c + kelvin_offset;

    // Pressure ratio (using standard atmosphere)
    double pressure_ratio = pow(1.0 - pressure_altitude_constant * pressure_altitude_ft, pressure_altitude_exponent);

    // Temperature ratio
    double temp_ratio = sea_level_temp_k / temp_k;

    // Density ratio: sigma = (P/P<sub>0</sub>) * (T<sub>0</sub>/T)
    double sigma = pressure_ratio * temp_ratio;

    return sigma;
}

// Calculate Equivalent Airspeed (EAS)
// EAS = TAS * sqrt(sigma)
double calculate_eas(double tas_kts,
                     double sigma)
{
    return tas_kts * sqrt(sigma);
}

// Calculate complete density altitude data
DensityAltitudeData calculate_density_altitude_data(double pressure_altitude_ft,  // Pressure altitude (feet)
                                                    double oat_celsius,           // Outside air temperature (Celsius)
                                                    double ias_kts,               // Indicated airspeed (knots)
                                                    double tas_kts)               // True airspeed (knots)
{
    DensityAltitudeData result;

    result.pressure_altitude_ft = pressure_altitude_ft;
    result.density_altitude_ft  = calculate_density_altitude(pressure_altitude_ft, oat_celsius);

    // ISA temperature at this altitude
    double isa_temp                = isa_temperature_c(pressure_altitude_ft);
    result.temperature_deviation_c = oat_celsius - isa_temp;

    // Air density ratio
    result.air_density_ratio = calculate_density_ratio(pressure_altitude_ft, oat_celsius);

    // Performance loss (inverse of density ratio)
    result.performance_loss_pct = (1.0 - result.air_density_ratio) * 100.0;

    // Equivalent airspeed
    result.eas_kts = calculate_eas(tas_kts, result.air_density_ratio);

    result.tas_to_ias_ratio = ias_kts > min_ias_for_ratio ? tas_kts / ias_kts : 1.0;

    // Pressure ratio
    result.pressure_ratio = pow(1.0 - pressure_altitude_constant * pressure_altitude_ft, pressure_altitude_exponent);

    return result;
}

// Output results as JSON
void print_json(const DensityAltitudeData& da)
{
    std::cout << std::fixed << std::setprecision(2) << "{\n"
              << "  \"density_altitude_ft\": " << da.density_altitude_ft << ",\n"
              << "  \"pressure_altitude_ft\": " << da.pressure_altitude_ft << ",\n"
              << "  \"air_density_ratio\": " << da.air_density_ratio << ",\n"
              << "  \"temperature_deviation_c\": " << da.temperature_deviation_c << ",\n"
              << "  \"performance_loss_pct\": " << da.performance_loss_pct << ",\n"
              << "  \"eas_kts\": " << da.eas_kts << ",\n"
              << "  \"tas_to_ias_ratio\": " << da.tas_to_ias_ratio << ",\n"
              << "  \"pressure_ratio\": " << da.pressure_ratio << "\n"
              << "}\n";
}

}  // namespace calc
}  // namespace airv

void print_usage(const char* program_name)
{
    std::cerr << "Usage: " << program_name << " <pressure_alt_ft> <oat_celsius> <ias_kts> <tas_kts> [force_error]\n"
              << "\n"
              << "Arguments:\n"
              << "  pressure_alt_ft : Pressure altitude (feet)\n"
              << "  oat_celsius     : Outside air temperature (Celsius)\n"
              << "  ias_kts        : Indicated airspeed (knots)\n"
              << "  tas_kts        : True airspeed (knots)\n"
              << "  force_error    : Optional, 1 to simulate error (default: 0)\n"
              << "\n"
              << "Example:\n"
              << "  " << program_name << " 5000 25 150 170\n"
              << "  (5000 ft PA, 25 Celsius OAT, 150 kts IAS, 170 kts TAS)\n";
}

int main(int argc,
         char* argv[])
{
    if (argc < 5 || 6 < argc)
    {
        print_usage(argv[0]);
        return static_cast<int>(airv::Return_code::invalid_argc);
    }

    double pressure_altitude_ft;  // Pressure altitude (feet)
    double oat_celsius;           // Outside air temperature (Celsius)
    double ias_kts;               // Indicated airspeed (knots)
    double tas_kts;               // True airspeed (knots)
    int32_t force_error = 0;

    // Parse optional force_error flag
    if (argc == 6 && !airv::utils::parse_int32(argv[5], force_error))
    {
        std::cerr << "Error: Invalid force_error flag\n";
        return static_cast<int>(airv::Return_code::parse_failed);
    }
    // Simulate error for error handling demonstration
    if (force_error == 1)
    {
        std::cerr << "Error: Simulated (forced) error\n";
        print_usage(argv[0]);
        return static_cast<int>(airv::Return_code::simulated);
    }
    if (!airv::utils::parse_double(argv[1], pressure_altitude_ft))
    {
        std::cerr << "Error: Invalid pressure altitude\n";
        return static_cast<int>(airv::Return_code::parse_failed);
    }
    if (!airv::utils::parse_double(argv[2], oat_celsius))
    {
        std::cerr << "Error: Invalid temperature\n";
        return static_cast<int>(airv::Return_code::parse_failed);
    }
    if (!airv::utils::parse_double(argv[3], ias_kts))
    {
        std::cerr << "Error: Invalid IAS\n";
        return static_cast<int>(airv::Return_code::parse_failed);
    }
    if (!airv::utils::parse_double(argv[4], tas_kts))
    {
        std::cerr << "Error: Invalid TAS\n";
        return static_cast<int>(airv::Return_code::parse_failed);
    }

    // Validate inputs
    if (pressure_altitude_ft < airv::calc::min_altitude_ft || pressure_altitude_ft > airv::calc::max_altitude_ft)
    {
        std::cerr << "Warning: Pressure altitude outside typical range\n";
    }
    if (oat_celsius < airv::calc::min_temperature_c || oat_celsius > airv::calc::max_temperature_c)
    {
        std::cerr << "Warning: Temperature outside typical range\n";
    }

    // Calculate and output results
    airv::calc::print_json(
        airv::calc::calculate_density_altitude_data(pressure_altitude_ft, oat_celsius, ias_kts, tas_kts));

    return static_cast<int>(airv::Return_code::success);
}