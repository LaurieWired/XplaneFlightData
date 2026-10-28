// Flight Performance Calculator for X-Plane MFD
// JSF AV C++ Coding Standard Compliant Version
//
// Performs advanced flight calculations:
// - Real-time wind vector with gust/turbulence analysis
// - Envelope margins (stall/overspeed/buffet)
// - Energy management (specific energy & trend)
// - Glide reach estimation

#include "xplane_mfd_calc.h"
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <iomanip>
#include <iostream>

namespace airv
{
namespace calc
{

// Fixed-size array limit
constexpr int32_t max_ias_history = 20;

// Calculation constants
constexpr double sqrt_two               = 1.414;  //! Not accurate
constexpr double typical_glide_ratio    = 12.0;
constexpr double best_glide_multiplier  = 1.3;
constexpr double typical_vs             = 60.0;
constexpr double energy_rate_divisor    = 101.27;
constexpr double energy_trend_threshold = 50.0;
constexpr double min_history_for_stats  = 2.0;

enum class Trend
{
    decreasing = -1,
    stable     = 0,
    increasing = 1,
};

struct Vector2D
{
    double x, y;

    Vector2D(double x_ = 0.0,
             double y_ = 0.0)
        : x(x_),
          y(y_)
    {
    }

    double magnitude() const { return sqrt(x * x + y * y); }

    Vector2D operator-(const Vector2D& other) const { return Vector2D(x - other.x, y - other.y); }
};

// Normalize angle to 0-360 range
double normalize_angle(double angle)
{
    double result = fmod(angle, units::angle_wrap);
    if (result < 0.0)
    {
        result += units::angle_wrap;
    }
    return result;
}

// Uses iterative formula to avoid overflow: C(n,k) = product(i=1 to k) (n-k+i)/i
uint64_t binomial_coefficient(uint32_t n,
                              uint32_t k)
{
    uint64_t result = 0;

    if (k > n)
    {
        result = 0;
    }
    else if (k == 0 || k == n)
    {
        result = 1;
    }
    else if (k == 1)
    {
        result = n;
    }
    else
    {
        // Optimize: C(n,k) = C(n, n-k), use smaller k
        if (k > n - k)
        {
            k = n - k;
        }

        // Iterative calculation to avoid overflow
        result = 1;
        for (uint32_t i = 1; i <= k; ++i)
        {
            result = result * (n - k + i) / i;
        }
    }

    return result;  // Single exit point
}

struct WindData
{
    double speed_kts;
    double direction_from;  // deg, where wind comes FROM
    double headwind;
    double crosswind;
    double gust_factor;
};

WindData calculate_wind_vector(double tas_kts,
                               double gs_kts,
                               double heading_deg,
                               double track_deg,
                               const double* ias_history,
                               int32_t history_size)
{
    WindData result;

    // Convert to vectors
    double heading_rad = heading_deg * units::deg_to_rad;
    double track_rad   = track_deg * units::deg_to_rad;

    // Air vector (TAS in heading direction)
    Vector2D air_vec(tas_kts * sin(heading_rad), tas_kts * cos(heading_rad));

    // Ground vector (GS in track direction)
    Vector2D ground_vec(gs_kts * sin(track_rad), gs_kts * cos(track_rad));

    // Wind = Ground - Air
    Vector2D wind_vec = ground_vec - air_vec;

    result.speed_kts = wind_vec.magnitude();

    // Wind direction (where FROM)
    double wind_dir_rad   = atan2(wind_vec.x, wind_vec.y);
    result.direction_from = normalize_angle(wind_dir_rad * units::rad_to_deg);

    // Components relative to track
    double wind_from_rel = normalize_angle(result.direction_from - track_deg);
    if (wind_from_rel > units::half_circle)
        wind_from_rel -= units::angle_wrap;

    double wind_from_rad = wind_from_rel * units::deg_to_rad;
    result.headwind      = -result.speed_kts * cos(wind_from_rad);
    result.crosswind     = result.speed_kts * sin(wind_from_rad);

    // Gust factor from IAS variance
    if (history_size >= min_history_for_stats)
    {
        double sum    = 0.0;
        double sum_sq = 0.0;
        for (int32_t i = 0; i < history_size; ++i)
        {
            sum += ias_history[i];
            sum_sq += ias_history[i] * ias_history[i];
        }
        double mean        = sum / history_size;
        double variance    = (sum_sq / history_size) - (mean * mean);
        double std_dev     = sqrt(variance);
        result.gust_factor = std_dev / mean;
    }
    else
    {
        result.gust_factor = 0.0;
    }

    return result;
}

struct EnvelopeMargins
{
    double stall_margin_pct;
    double vmo_margin_pct;
    double mmo_margin_pct;
    double min_margin_pct;
    double load_factor;
    double corner_speed_kts;
};

EnvelopeMargins calculate_envelope(double bank_deg,  // Bank angle (deg)
                                   double ias_kts,   // Indicated airspeed (knots)
                                   double mach,      // Mach number
                                   double vso_kts,   // Stall speed in landing config (knots IAS)
                                   double vne_kts,   // Velocity never exceed (knots IAS)
                                   double mmo)       // Maximum operating Mach number
{
    EnvelopeMargins result;

    // Load factor
    double bank_rad    = bank_deg * units::deg_to_rad;
    result.load_factor = 1.0 / cos(bank_rad);

    // Stall speed increases with load factor
    double vs_actual        = vso_kts * sqrt(result.load_factor);
    result.stall_margin_pct = ((ias_kts - vs_actual) / vs_actual) * 100.0;

    // VMO margin
    result.vmo_margin_pct = ((vne_kts - ias_kts) / vne_kts) * 100.0;

    // MMO margin
    result.mmo_margin_pct = ((mmo - mach) / mmo) * 100.0;

    // Minimum margin
    result.min_margin_pct = std::min({result.stall_margin_pct, result.vmo_margin_pct, result.mmo_margin_pct});

    // Corner speed estimate
    result.corner_speed_kts = vs_actual * sqrt_two;  // Vc is almost Vs * sqrt(2)

    return result;
}

struct EnergyData
{
    double specific_energy_ft;
    double energy_rate_kts;
    Trend trend;  // 1=increasing, 0=stable, -1=decreasing
};

EnergyData calculate_energy(double tas_kts,
                            double altitude_ft,
                            double vs_fpm)
{
    EnergyData result;

    // Specific energy: Es = h + pow(V, 2)/(2g)
    double v_ms               = tas_kts * units::kts_to_ms;
    double h_m                = altitude_ft * units::ft_to_m;
    double kinetic_energy_m   = (v_ms * v_ms) / (2.0 * units::gravity);
    double total_energy_m     = h_m + kinetic_energy_m;
    result.specific_energy_ft = total_energy_m * units::m_to_ft;

    // Energy rate (convert VS to equivalent airspeed change)
    result.energy_rate_kts = vs_fpm / energy_rate_divisor;  // Simplified

    // Trend
    if (vs_fpm > energy_trend_threshold)
    {
        result.trend = Trend::increasing;
    }
    else if (vs_fpm < -energy_trend_threshold)
    {
        result.trend = Trend::decreasing;
    }
    else
    {
        result.trend = Trend::stable;
    }

    return result;
}

struct GlideData
{
    double still_air_range_nm;
    double wind_adjusted_range_nm;
    double glide_ratio;
    double best_glide_speed_kts;
};

GlideData calculate_glide_reach(double agl_ft,
                                double tas_kts,
                                double headwind_kts)
{
    GlideData result;

    // Assume typical L/D ratio of 12:1 for general aviation
    result.glide_ratio = typical_glide_ratio;

    // Still air range
    double range_ft           = agl_ft * result.glide_ratio;
    result.still_air_range_nm = range_ft / units::nm_to_ft;

    // Wind adjustment (simplified)
    double wind_effect            = headwind_kts / tas_kts;
    result.wind_adjusted_range_nm = result.still_air_range_nm * (1.0 - wind_effect);

    // Best glide speed (simplified estimate)
    result.best_glide_speed_kts = best_glide_multiplier * typical_vs;  // 1.3 * typical Vs

    return result;
}

// Output comprehensive JSON results
void print_json_results(const WindData& wind,
                        const EnvelopeMargins& envelope,
                        const EnergyData& energy,
                        const GlideData& glide)
{
    std::cout << std::fixed << std::setprecision(2);
    std::cout << "{\n";

    // Wind
    std::cout << "  \"wind\": {\n";
    std::cout << "    \"speed_kts\": " << wind.speed_kts << ",\n";
    std::cout << "    \"direction_from\": " << wind.direction_from << ",\n";
    std::cout << "    \"headwind\": " << wind.headwind << ",\n";
    std::cout << "    \"crosswind\": " << wind.crosswind << ",\n";
    std::cout << "    \"gust_factor\": " << wind.gust_factor << "\n";
    std::cout << "  },\n";

    // Envelope
    std::cout << "  \"envelope\": {\n";
    std::cout << "    \"stall_margin_pct\": " << envelope.stall_margin_pct << ",\n";
    std::cout << "    \"vmo_margin_pct\": " << envelope.vmo_margin_pct << ",\n";
    std::cout << "    \"mmo_margin_pct\": " << envelope.mmo_margin_pct << ",\n";
    std::cout << "    \"min_margin_pct\": " << envelope.min_margin_pct << ",\n";
    std::cout << "    \"load_factor\": " << envelope.load_factor << ",\n";
    std::cout << "    \"corner_speed_kts\": " << envelope.corner_speed_kts << "\n";
    std::cout << "  },\n";

    // Energy
    std::cout << "  \"energy\": {\n";
    std::cout << "    \"specific_energy_ft\": " << energy.specific_energy_ft << ",\n";
    std::cout << "    \"energy_rate_kts\": " << energy.energy_rate_kts << ",\n";
    std::cout << "    \"trend\": " << static_cast<int32_t>(energy.trend) << "\n";
    std::cout << "  },\n";

    // Glide
    std::cout << "  \"glide\": {\n";
    std::cout << "    \"still_air_range_nm\": " << glide.still_air_range_nm << ",\n";
    std::cout << "    \"wind_adjusted_range_nm\": " << glide.wind_adjusted_range_nm << ",\n";
    std::cout << "    \"glide_ratio\": " << glide.glide_ratio << ",\n";
    std::cout << "    \"best_glide_speed_kts\": " << glide.best_glide_speed_kts << "\n";
    std::cout << "  },\n";

    // Alternate airport combinations (JSF-compliant iterative binomial)
    std::cout << "  \"alternate_airports\": {\n";
    std::cout << "    \"combinations_5_choose_2\": " << binomial_coefficient(5, 2) << ",\n";
    std::cout << "    \"combinations_10_choose_3\": " << binomial_coefficient(10, 3) << ",\n";
    std::cout << "    \"note\": \"Iterative binomial calculation (JSF-compliant, no recursion)\"\n";
    std::cout << "  }\n";

    std::cout << "}\n";
}

// Ring buffer for managing sensor history.
struct SensorHistoryBuffer
{
    //  The pre-allocated, fixed-size buffer.
    std::array<double, max_ias_history> data;

    int32_t head_index   = 0;
    int32_t current_size = 0;

    void add_reading(double new_ias)
    {
        data[head_index] = new_ias;

        // Move the head to the next position, wrapping around if necessary.
        head_index = (head_index + 1) % max_ias_history;

        // The buffer size grows until it's full.
        if (current_size < max_ias_history)
        {
            current_size++;
        }
    }

    const double* get_data_ptr() const { return data.data(); }

    int32_t get_size() const { return current_size; }
};

}  // namespace calc
}  // namespace airv

int main(int argc,
         char* argv[])
{
    if (argc != 15)
    {
        std::cerr << "Usage: " << argv[0]
                  << " <tas_kts> <gs_kts> <heading> <track> <ias_kts> <mach> <altitude_ft> <agl_ft> <vs_fpm> "
                     "<weight_kg> <bank_deg> <vso_kts> <vne_kts> <mmo>\n";
        std::cerr << "Arguments:\n";
        std::cerr << "  tas_kts    : True airspeed (knots)\n";
        std::cerr << "  gs_kts     : Ground speed (knots)\n";
        std::cerr << "  heading    : Heading (deg)\n";
        std::cerr << "  track      : Ground track (deg)\n";
        std::cerr << "  ias_kts    : Indicated airspeed (knots)\n";
        std::cerr << "  mach       : n";
        std::cerr << "  altitude_ft: Altitude (feet)\n";
        std::cerr << "  agl_ft     : Above ground level (feet)\n";
        std::cerr << "  vs_fpm     : Vertical speed (feet/min)\n";
        std::cerr << "  weight_kg  : Aircraft weight (kg)\n";
        std::cerr << "  bank_deg   : Bank angle (deg)\n";
        std::cerr << "  vso_kts    : Stall speed in landing config (knots IAS)\n";
        std::cerr << "  vne_kts    : Velocity never exceed (knots IAS)\n";
        std::cerr << "  mmo        : Maximum operating Mach number\n";
        std::cerr << "  course_change_deg: Course change (degrees)\n\n";
        std::cerr << "Example:\n";
        std::cerr << "  " << argv[0] << " 250 245 90 95 220 0.65 35000 35000 -500 75000 5 120 250 0.82\n";
        return static_cast<int>(airv::Return_code::invalid_argc);
    }

    double tas_kts;      // True airspeed (knots)
    double gs_kts;       // Ground speed (knots)
    double heading;      // Heading (deg)
    double track;        // Ground track (deg)
    double ias_kts;      // Indicated airspeed (knots)
    double mach;         // Mach number
    double altitude_ft;  // Altitude (feet)
    double agl_ft;       // Above ground level (feet)
    double vs_fpm;       // Vertical speed (feet/min)
    double weight_kg;    // Aircraft weight (kg)
    double bank_deg;     // Bank angle (deg)
    double vso_kts;      // Stall speed in landing config (knots IAS)
    double vne_kts;      // Velocity never exceed (knots IAS)
    double mmo;          // Maximum operating Mach number

    //? Why are there no custom messages for the arguments like in density altitude calculator?
    //? No simulated error?
    if (!airv::utils::parse_double(argv[1], tas_kts) || !airv::utils::parse_double(argv[2], gs_kts) ||
        !airv::utils::parse_double(argv[3], heading) || !airv::utils::parse_double(argv[4], track) ||
        !airv::utils::parse_double(argv[5], ias_kts) || !airv::utils::parse_double(argv[6], mach) ||
        !airv::utils::parse_double(argv[7], altitude_ft) || !airv::utils::parse_double(argv[8], agl_ft) ||
        !airv::utils::parse_double(argv[9], vs_fpm) || !airv::utils::parse_double(argv[10], weight_kg) ||
        !airv::utils::parse_double(argv[11], bank_deg) || !airv::utils::parse_double(argv[12], vso_kts) ||
        !airv::utils::parse_double(argv[13], vne_kts) || !airv::utils::parse_double(argv[14], mmo))
    {
        std::cerr << "Error: Invalid numeric argument\n";
        return static_cast<int>(airv::Return_code::parse_failed);
    }
    airv::calc::SensorHistoryBuffer ias_buffer;

    for (int32_t i = 0; i < 30; ++i)
    {
        double new_reading = 150.0 + (i % 7) - 3.0;

        ias_buffer.add_reading(new_reading);
    }

    // Calculate and output results
    airv::calc::WindData wind = airv::calc::calculate_wind_vector(
        tas_kts, gs_kts, heading, track, ias_buffer.get_data_ptr(), ias_buffer.get_size());
    airv::calc::EnvelopeMargins envelope =
        airv::calc::calculate_envelope(bank_deg, ias_kts, mach, vso_kts, vne_kts, mmo);
    airv::calc::EnergyData energy = airv::calc::calculate_energy(tas_kts, altitude_ft, vs_fpm);
    airv::calc::GlideData glide   = airv::calc::calculate_glide_reach(agl_ft, tas_kts, wind.headwind);
    airv::calc::print_json_results(wind, envelope, energy, glide);

    return static_cast<int>(airv::Return_code::success);
}