#include "pch.h"
#include "CircuitView.h"
#include "OmarchyTable.h"
#include "OmarchyTheme.h"
#include "pb.h"
#include "TPinballTable.h"
#include "TFlipper.h"
#include "TFlipperEdge.h"
#include "TBall.h"
#include "TPlunger.h"
#include "winmain.h"
#include "options.h"
#include "SDL_image.h"
#include "../native/BrandWordmark.h"
#include <algorithm>
#include <string>
#ifndef CIRCUIT_SOURCE_DIR
#define CIRCUIT_SOURCE_DIR "assets/circuit"
#endif
#ifndef CIRCUIT_INSTALL_DIR
#define CIRCUIT_INSTALL_DIR "/usr/share/omarchy-spacecadet/circuit"
#endif
namespace CircuitView {
namespace {
SDL_Texture *board=nullptr,*wordmark=nullptr;
SDL_Surface* original=nullptr;
SDL_Renderer* renderer=nullptr;
uint32_t lastAccent=0;
float scale,ox,oy;
ImDrawList* draw;
ImVec2 p(float x,float y){return {ox+x*scale,oy+y*scale};}
ImU32 rgba(int r,int g,int b,int a=255){return IM_COL32(r,g,b,a);}
ImU32 accent(int a=255){auto c=OmarchyTheme::Accent();return rgba((c>>16)&255,(c>>8)&255,c&255,a);}
void disc(float x,float y,float r,ImU32 c){draw->AddCircleFilled(p(x,y),r*scale,c,24);}
void lamp(float x,float y,bool on,float radius=9){
 if(on){disc(x,y,radius+8,accent(15));disc(x,y,radius+4,accent(35));disc(x,y,radius,accent());disc(x-2,y-2,radius*.5f,rgba(238,249,213));}
}
void label(float x,float y,const char* text,float size=18,ImU32 c=IM_COL32(220,221,202,255)){
 draw->AddText(ImGui::GetFont(),size*scale,p(x,y),c,text);
}
// A small legible 5x7 dot-matrix alphabet; rendering stays sharp at every window size.
const char* glyph(char c){
 switch(c){
#define G(c,s) case c:return s
 G('0',"0E11131519110E");G('1',"040C040404040E");G('2',"0E11010204081F");G('3',"1E01010601011E");G('4',"02060A121F0202");G('5',"1F10101E01011E");G('6',"0610101E11110E");G('7',"1F010204080808");G('8',"0E11110E11110E");G('9',"0E11110F01010C");
 G('A',"0E11111F111111");G('B',"1E11111E11111E");G('C',"0E11101010110E");G('D',"1E11111111111E");G('E',"1F10101E10101F");G('F',"1F10101E101010");G('G',"0E11101711110F");G('H',"1111111F111111");G('I',"0E04040404040E");G('J',"0702020212120C");G('K',"11121418141211");G('L',"1010101010101F");G('M',"111B1515111111");G('N',"11191513111111");G('O',"0E11111111110E");G('P',"1E11111E101010");G('Q',"0E11111115120D");G('R',"1E11111E141211");G('S',"0F10100E01011E");G('T',"1F040404040404");G('U',"1111111111110E");G('V',"11111111110A04");G('W',"11111115151B11");G('X',"11110A040A1111");G('Y',"11110A04040404");G('Z',"1F01020408101F");G('+',"0004041F040400");G('-',"0000001F000000");G('/',"01010204081010");G(':',"00040000040000");
#undef G
 default:return "00000000000000";
 }
}
void matrix(float x,float y,float w,float h,const std::string& text,float dot){
 auto hex=[](char c){return c<='9'?c-'0':c-'A'+10;};
 float width=(text.size()*6-1)*dot;float start=x+(w-width)/2,top=y+(h-7*dot)/2;
 for(size_t i=0;i<text.size();i++){auto g=glyph(text[i]);for(int row=0;row<7;row++){int bits=hex(g[row*2])*16+hex(g[row*2+1]);for(int col=0;col<5;col++)if(bits&(1<<(4-col))){float xx=start+(i*6+col)*dot,yy=top+row*dot;disc(xx,yy,dot*.61f,rgba(255,120,15,22));disc(xx,yy,dot*.36f,rgba(255,185,72));}}}
}
void capsule(float x,float y,float xx,float yy,float r,ImU32 c){float len=std::hypot(xx-x,yy-y),nx=-(yy-y)/len,ny=(xx-x)/len,tip=r*.65f;
 ImVec2 q[]={p(x+nx*r,y+ny*r),p(xx+nx*tip,yy+ny*tip),p(xx-nx*tip,yy-ny*tip),p(x-nx*r,y-ny*r)};draw->AddConvexPolyFilled(q,4,c);disc(x,y,r,c);disc(xx,yy,tip,c);}
// The board is one rectangular image. Copy it directly instead of expanding it
// into textured triangles in the software renderer. Keep it in the ImGui draw
// order so the mechanisms, lamps and menus are still composited above it.
void drawBoard(const ImDrawList*, const ImDrawCmd*){
 SDL_FRect destination={ox,oy,1536*scale,1024*scale};
 SDL_RenderCopyF(renderer,board,nullptr,&destination);
}
void updateTexture(){
 uint32_t c=OmarchyTheme::Accent();if(c==lastAccent&&board)return;lastAccent=c;
 auto surface=SDL_ConvertSurfaceFormat(original,SDL_PIXELFORMAT_ARGB8888,0);auto pixels=(uint32_t*)surface->pixels;
 // Recolour green glass and lamps only. Ivory, chrome, black and amber keep their materials.
 float ar=((c>>16)&255)/255.f,ag=((c>>8)&255)/255.f,ab=(c&255)/255.f;
 for(int y=0;y<surface->h;y++)for(int x=0;x<surface->w;x++){
  auto& q=pixels[y*surface->pitch/4+x];float r=((q>>16)&255)/255.f,g=((q>>8)&255)/255.f,b=(q&255)/255.f;
  float amount=std::max(0.f,std::min(1.f,(g-std::max(r,b))/.15f));
  float bright=std::max(r,std::max(g,b));
  if(amount>.02f){int rr=(int)(255*(r*(1-amount)+ar*bright*amount));int gg=(int)(255*(g*(1-amount)+ag*bright*amount));int bb=(int)(255*(b*(1-amount)+ab*bright*amount));q=0xff000000|(rr<<16)|(gg<<8)|bb;}
 }
 if(board)SDL_DestroyTexture(board);board=SDL_CreateTextureFromSurface(renderer,surface);SDL_FreeSurface(surface);
}
}
bool Init(SDL_Renderer* r){
 renderer=r;char* base=SDL_GetBasePath();
 std::vector<std::string> dirs={CIRCUIT_INSTALL_DIR,std::string(base?base:"")+"../../share/omarchy-retro-arcade/circuit",CIRCUIT_SOURCE_DIR};SDL_free(base);
 if(const char* dir=getenv("OMARCHY_CIRCUIT_ASSETS"))dirs.insert(dirs.begin(),dir);
 for(const auto& dir:dirs){original=IMG_Load((dir+"/table.png").c_str());if(original)break;}
 if(!original){SDL_Log("Cannot load Circuit artwork: %s",IMG_GetError());return false;}
 SDL_SetHint(SDL_HINT_RENDER_SCALE_QUALITY,"1");
 auto surface=SDL_CreateRGBSurfaceWithFormat(0,4131,950,32,SDL_PIXELFORMAT_RGBA32);
 if(!surface)return false;
 SDL_FillRect(surface,nullptr,SDL_MapRGBA(surface->format,0,0,0,0));
 for(const auto& r:BrandWordmark){SDL_Rect rect={r[0],r[1],r[2],r[3]};SDL_FillRect(surface,&rect,SDL_MapRGBA(surface->format,158,206,106,255));}
 wordmark=SDL_CreateTextureFromSurface(renderer,surface);SDL_FreeSurface(surface);
 updateTexture();return board&&wordmark;
}
void Draw(){
 if(!board||!pb::MainTable)return;updateTexture();draw=ImGui::GetBackgroundDrawList();
 auto size=ImGui::GetIO().DisplaySize;float menu=options::Options.ShowMenu?winmain::MainMenuHeight:0;
 scale=std::min(size.x/1536.f,(size.y-menu)/1024.f);ox=(size.x-1536*scale)/2;oy=menu+(size.y-menu-1024*scale)/2;
 draw->AddRectFilled({0,menu},size,rgba(5,8,8));draw->AddCallback(drawBoard,nullptr);
 // Exact official wordmark geometry, proportionally placed after material tinting.
 const float wordScale=144.f/4131.f,wordX=562-72,wordY=520-950*wordScale/2;
 draw->AddImage((ImTextureID)wordmark,p(wordX,wordY),p(wordX+144,wordY+950*wordScale));
 auto t=pb::MainTable;
 const float lamps[12][2]={{562,422},{626,438},{664,478},{674,525},{659,565},{618,599},{562,617},{507,599},{464,565},{450,526},{458,479},{498,439}};
 for(unsigned i=0;i<12;i++)lamp(lamps[i][0],lamps[i][1],i<OmarchyTable::Progress());
 const float xs[]={470,617,563,202},ys[]={226,202,287,431};
 for(int i=0;i<4;i++){std::string n="bumper"+std::to_string(i);float f=OmarchyTable::Flash(n.c_str());if(f>0){draw->AddCircle(p(xs[i],ys[i]),(i==3?33:44)*scale,accent((int)(f*230)),32,5*scale);disc(xs[i],ys[i]-15,16,rgba(255,241,179,(int)(f*100)));}}
 for(int i=0;i<8;i++){float x=i<4?504+i*31:747-(i-4)*8,y=i<4?117:319+(i-4)*25;lamp(x,y,(OmarchyTable::Targets()&(1u<<i))!=0,7);}
 for(int i=0;i<2;i++){std::string name=i?"sling_right":"sling_left";float f=OmarchyTable::Flash(name.c_str());if(f>0)draw->AddLine(p(i?755:295,635),p(i?690:360,778),accent((int)(f*220)),5*scale);}
 // Flipper endpoints come from the engine's current collision edge, not a UI animation.
 for(auto flipper:t->FlipperList){auto e=flipper->FlipperEdge;float x=540+e->RotOrigin.X*25,y=500+e->RotOrigin.Y*25;
  float dx=e->T1Src.X-e->RotOrigin.X,dy=e->T1Src.Y-e->RotOrigin.Y;
  float a=e->CurrentAngle,xx=x+(dx*cos(a)-dy*sin(a))*25,yy=y+(dx*sin(a)+dy*cos(a))*25;
  capsule(x+5,y+10,xx+5,yy+10,18,rgba(0,0,0,150));capsule(x,y,xx,yy,18,rgba(37,42,34));
  capsule(x,y-3,xx,yy-3,15,rgba(173,168,132));capsule(x,y-6,xx,yy-6,12,rgba(229,226,196));
  capsule(x+2,y+10,xx,yy+8,3,accent());disc(x,y-5,10,rgba(58,61,52));disc(x-2,y-7,7,rgba(210,212,193));disc(x-4,y-9,3,rgba(253,251,226));
 }
 for(auto ball:t->BallList)if(ball->ActiveFlag){float x=540+ball->Position.X*25,y=500+ball->Position.Y*25-ball->Position.Z*7,r=ball->Radius*25;
  disc(x+5,y+10,r+2,rgba(0,0,0,155));disc(x,y,r+1,rgba(204,211,205));disc(x,y,r,rgba(29,36,38));
  disc(x-2,y-3,r*.82f,rgba(126,145,146));disc(x+2,y+3,r*.68f,rgba(33,46,47));disc(x-3,y-4,r*.55f,rgba(213,227,220));disc(x-4,y-5,r*.3f,rgba(255,255,241));
 }
 float pull=t->Plunger->PullbackStartedFlag?std::min(1.f,t->Plunger->Boost/100):0;
 draw->AddRectFilled(p(930,935+pull*35),p(977,951+pull*35),rgba(180,185,172),3*scale);
 char score[32];snprintf(score,sizeof(score),"%07d",std::max(0,t->CurScore));matrix(1067,554,414,67,score,7);
 std::string ball=OmarchyTable::GameOver()?"GAME OVER":"BALL "+std::to_string(4-std::max(1,t->BallCount));matrix(1067,638,414,56,ball,4.5f);
 const char* status=winmain::single_step?"PAUSED  P RESUME":OmarchyTable::Status();matrix(1067,714,414,66,status,3.25f);
 label(1090,820,"CIRCUIT",19);label(1300,820,"TARGET BANK",19);
 label(1090,852,(std::to_string(OmarchyTable::Progress())+" / 12").c_str(),23);unsigned count=0;for(unsigned v=OmarchyTable::Targets();v;v>>=1)count+=v&1;
 label(1300,852,(std::to_string(count)+" / 8").c_str(),23);
 label(1090,899,("ORBITS  "+std::to_string(OmarchyTable::Orbits())).c_str(),18);label(1300,899,("RAMPS  "+std::to_string(OmarchyTable::Ramps())).c_str(),18);
 label(1080,950,"A / D FLIPPERS    SPACE LAUNCH",17);
 label(1110,48,"OMARCHY ARCADE  /  PINBALL",18);
}
void Shutdown(){SDL_DestroyTexture(board);SDL_DestroyTexture(wordmark);SDL_FreeSurface(original);board=wordmark=nullptr;original=nullptr;lastAccent=0;}
}
