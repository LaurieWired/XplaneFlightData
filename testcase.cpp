//! Only for testing outputs, not compliant

#include <fstream>
#include <iostream>
#include <sstream>
#include <string>

int main(int          argc,
         const char** argv)
{
    std::cin.sync_with_stdio(false);
    if (argc == 1)
    {
        std::cerr << "Usage: <program> | " << argv[0] << " <expected output>\n";
        return -1;
    }
    std::ifstream f(argv[1]);
    if (!f)
    {
        std::cerr << "File not found\n";
        return -1;
    }
    std::stringstream ss;
    ss << f.rdbuf();
    std::string a, b;
    bool        ret = false;
    while (std::getline(std::cin, a))
    {
        if (!(std::getline(ss, b)) || a != b)
        {
            ret = true;
        }
        std::cout << a << '\n';
    }
    if (std::getline(ss, b))
    {
        ret = true;
    }
    return ret;
}