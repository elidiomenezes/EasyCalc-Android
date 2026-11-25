#include "iso8583_parser.hpp"
#include <array>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <vector>
using namespace payment_gateway;
using Kind=FieldFormat;
struct Spec { unsigned de; Kind kind; size_t width; };
const std::vector<Spec> specs={{2,Kind::llvar,19},{3,Kind::fixed,6},{4,Kind::fixed,12},{5,Kind::fixed,12},{7,Kind::fixed,10},{9,Kind::fixed,8},{11,Kind::fixed,6},{12,Kind::fixed,6},{13,Kind::fixed,4},{14,Kind::fixed,4},{15,Kind::fixed,4},{16,Kind::fixed,4},{18,Kind::fixed,4},{22,Kind::fixed,3},{23,Kind::fixed,3},{25,Kind::fixed,2},{26,Kind::fixed,2},{28,Kind::fixed,9},{29,Kind::fixed,9},{30,Kind::fixed,9},{31,Kind::fixed,9},{32,Kind::llvar,11},{33,Kind::llvar,11},{35,Kind::llvar,37},{37,Kind::fixed,12},{38,Kind::fixed,6},{39,Kind::fixed,2},{40,Kind::fixed,3},{41,Kind::fixed,8},{42,Kind::fixed,15},{43,Kind::fixed,40},{44,Kind::llvar,25},{45,Kind::llvar,76},{48,Kind::lllvar,999},{49,Kind::fixed,3},{50,Kind::fixed,3},{52,Kind::fixed,16},{53,Kind::fixed,96},{54,Kind::lllvar,120},{55,Kind::lllvar,510},{56,Kind::lllvar,4},{58,Kind::lllvar,11},{59,Kind::lllvar,255},{60,Kind::lllvar,999},{62,Kind::lllvar,999},{63,Kind::llllvar,9999},{64,Kind::fixed,64},{67,Kind::fixed,2},{70,Kind::fixed,3},{90,Kind::fixed,42},{95,Kind::fixed,42},{98,Kind::fixed,25},{100,Kind::llvar,11},{102,Kind::llvar,28},{103,Kind::llvar,28},{123,Kind::lllvar,15},{124,Kind::llllvar,9999},{128,Kind::fixed,64}};
size_t assertions=0;
void check(bool x, const std::string& why) { ++assertions; if(!x) throw std::runtime_error(why); }
template<class F> void must_fail(F&& f,const std::string& why) {
    ++assertions;
    try { f(); } catch (const ParseError&) {return;}
    throw std::runtime_error("accepted invalid wire: "+why);
}
std::string digits(size_t n,unsigned width) {
    std::string out(width,'0');
    for(unsigned i=0;i<width;++i){out[width-i-1]=static_cast<char>('0'+n%10);n/=10;}
    if(n) throw std::runtime_error("oversize test number");
    return out;
}
std::string bitmap(const std::vector<unsigned>& des){
    std::array<bool,129> flags{};
    unsigned hi=64;
    for(unsigned de:des){flags[de]=true;if(de>64)hi=128;}
    if(hi==128) flags[1]=true;
    std::string out; const char* hex="0123456789ABCDEF";
    for(unsigned start=1;start<=hi;start+=4){unsigned n=0;for(unsigned j=0;j<4;++j)if(flags[start+j])n|=8U>>j;out+=hex[n];}
    return out;
}
unsigned prefix(Kind k) {return k==Kind::llvar?2:k==Kind::lllvar?3:k==Kind::llllvar?4:0;}
std::string value_wire(const Spec& e,const std::string& v){
    const unsigned n=prefix(e.kind);
    return (n?digits(v.size(),n):std::string{})+v;
}
std::string wire(const Spec& e,const std::string& v){return "0200"+bitmap({e.de})+value_wire(e,v);}
void single_field(const Spec& e){
    const Iso8583Parser parser;
    auto table=Iso8583Parser::nibss_fields();
    check(table[e.de].format==e.kind && table[e.de].maximum==e.width,"wrong table DE"+std::to_string(e.de));
    std::string v(e.kind==Kind::fixed?e.width:3,'Q');
    auto valid=wire(e,v);
    const auto parsed=parser.parse(valid);
    check(parsed.mti=="0200" && parsed.present[e.de] && parsed.fields[e.de]==v,"single field DE"+std::to_string(e.de));
    for(unsigned i=2;i<=128;++i) if(i!=e.de) check(!parsed.present[i],"unexpected DE"+std::to_string(i));
    must_fail([&]{parser.parse(valid+"!");},"trailing DE"+std::to_string(e.de));
    must_fail([&]{parser.parse(valid.substr(0,valid.size()-1));},"truncated DE"+std::to_string(e.de));
    if(auto n=prefix(e.kind)){
        check(parser.parse(wire(e,"")).present[e.de],"zero length DE"+std::to_string(e.de));
        check(parser.parse(wire(e,std::string(e.width,'Z'))).fields[e.de].size()==e.width,"max DE"+std::to_string(e.de));
        if(e.width<(n==2?99U:n==3?999U:9999U)) {
            auto big=wire(e,std::string(e.width+1,'Y'));
            must_fail([&]{parser.parse(big);},"above max DE"+std::to_string(e.de));
        }
        auto bad="0200"+bitmap({e.de})+std::string(n,'X')+"ABC";
        must_fail([&]{parser.parse(bad);},"nondigit prefix DE"+std::to_string(e.de));
        auto truncated="0200"+bitmap({e.de})+digits(4,n)+"ABC";
        must_fail([&]{parser.parse(truncated);},"truncated prefix payload DE"+std::to_string(e.de));
        std::string binary("A\0B",3);
        check(parser.parse(wire(e,binary)).fields[e.de]==binary,"embedded null DE"+std::to_string(e.de));
    }
}
void test_all_fields(){
    const auto tab=Iso8583Parser::nibss_fields();
    size_t count=0;for(auto x:tab) if(x.format!=Kind::unused) ++count;
    check(count==58,"not 58 fields");
    check(tab[70].format==Kind::fixed && tab[70].maximum==3,"DE70 format");
    for(const auto& e:specs)single_field(e);
    std::vector<unsigned> des;std::string payload="0200";
    for(const auto& e:specs) des.push_back(e.de);
    payload+=bitmap(des);
    for(const auto& e:specs)payload+=value_wire(e,std::string(e.kind==Kind::fixed?e.width:3,static_cast<char>('A'+e.de%26)));
    auto parsed=Iso8583Parser{}.parse(payload);
    for(const auto& e:specs)check(parsed.fields[e.de]==std::string(e.kind==Kind::fixed?e.width:3,static_cast<char>('A'+e.de%26)),"all together DE"+std::to_string(e.de));
    must_fail([&]{Iso8583Parser{}.parse(payload+"X");},"all fields trailing");
    must_fail([&]{Iso8583Parser{}.parse(payload.substr(0,payload.size()-1));},"all fields truncated");
}
void other_errors(){
    Iso8583Parser parser;
    must_fail([&]{parser.parse("");},"empty");
    must_fail([&]{parser.parse("ABC");},"short mti");
    must_fail([&]{parser.parse("A200"+bitmap({3})+"123456");},"bad mti");
    must_fail([&]{parser.parse("0200GGGGGGGGGGGGGGGG");},"bad primary bitmap");
    must_fail([&]{parser.parse("02008000000000000000GGGGGGGGGGGGGGGG");},"bad secondary bitmap");
    must_fail([&]{parser.parse("02008000000000000000");},"missing secondary bitmap");
    const auto signon="0800"+bitmap({70})+"001";
    check(parser.parse(signon).fields[70]=="001","sign-on DE70");
    check(parser.compose(parser.parse(signon))==signon,"sign-on round trip");
    must_fail([&]{parser.parse("0200"+bitmap({6})+"000000000001");},"unsupported DE6");
    must_fail([&]{parser.parse("0200"+bitmap({3})+"123456X");},"trailing byte");
    size_t offset=std::numeric_limits<size_t>::max();
    must_fail([&]{Iso8583Parser::parse_fixed("abc",offset,1);},"cursor overflow");
    check(offset==std::numeric_limits<size_t>::max(),"cursor modified on error");
    offset=0;
    must_fail([&]{Iso8583Parser::parse_llvar("XX",offset,99);},"LLVAR invalid prefix");
    check(offset==0,"cursor modified on failed LLVAR");
    offset=0;
    must_fail([&]{Iso8583Parser::parse_llllvar("0004ABC",offset,9999);},"LLLLVAR truncated");
    check(offset==0,"cursor modified on failed LLLLVAR");
    std::string b("0003A\0B",7);offset=0;
    check(Iso8583Parser::parse_llllvar(b,offset,9999)==std::string("A\0B",3) && offset==7,"binary LLLLVAR");
    offset=0;
    must_fail([&]{Iso8583Parser::parse_bitmaps("GGGGGGGGGGGGGGGG",offset);},"bitmap hex");
    check(offset==0,"cursor modified on bad bitmap");
}
int main(){
    try { test_all_fields();other_errors();std::cout<<"PASS: 58 DEs independently, combined 58-DE message, malformed inputs; "<<assertions<<" assertions\n"; }
    catch(const std::exception& ex){std::cerr<<"FAIL: "<<ex.what()<<" after "<<assertions<<" assertions\n";return 1;}
}
