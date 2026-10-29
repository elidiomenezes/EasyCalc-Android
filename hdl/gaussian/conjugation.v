// Gaussian integers modulo 2^W. Experimental combinational reference designs.
// Inputs are Gaussian 2-adic units (a+b odd). All arithmetic wraps modulo 2^W.
module conjugate_direct #(parameter W=16)(
 input wire [W-1:0] a,b, output wire [W-1:0] re,im);
 assign re=a;
 assign im=-b;
endmodule

module conjugate_newton #(parameter W=16)(
 input wire [W-1:0] a,b, output reg [W-1:0] re,im);
 // Newton inverse in Z_2[i], then multiply by norm.
 // Seed inverse modulo 2: 1 if a odd; -i if b odd.
 localparam STEPS=$clog2(W);
 reg [W-1:0] xr,xi,pr,pi,er,ei,norm;
 integer j;
 always @* begin
   xr=a[0] ? {{(W-1){1'b0}},1'b1} : {W{1'b0}};
   xi=a[0] ? {W{1'b0}} : {W{1'b1}};
   for(j=0;j<STEPS;j=j+1) begin
     pr=a*xr-b*xi;
     pi=a*xi+b*xr;
     er=2-pr;
     ei=-pi;
     pr=xr*er-xi*ei;
     pi=xr*ei+xi*er;
     xr=pr;
     xi=pi;
   end
   norm=a*a+b*b;
   re=norm*xr;
   im=norm*xi;
 end
endmodule

module conjugate_norm_inverse #(parameter W=16)(
 input wire [W-1:0] a,b, output reg [W-1:0] re,im);
 // Scalar Newton inverse of norm, then norm*(a,-b)*inverse(norm).
 // This deliberately exposes a redundant alternative for synthesis comparison.
 localparam STEPS=$clog2(W);
 reg [W-1:0] norm,inv;
 integer j;
 always @* begin
   norm=a*a+b*b;
   inv=1;
   for(j=0;j<STEPS;j=j+1)
     inv=inv*(2-norm*inv);
   re=(a*norm)*inv;
   im=(-b*norm)*inv;
 end
endmodule
