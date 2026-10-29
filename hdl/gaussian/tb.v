module tb;
 parameter W=16;
 reg [W-1:0] a,b;
 wire [W-1:0] dr,di,nr,ni,sr,si;
 integer k,errors;
 conjugate_direct #(.W(W)) d(a,b,dr,di);
 conjugate_newton #(.W(W)) n(a,b,nr,ni);
 conjugate_norm_inverse #(.W(W)) s(a,b,sr,si);
 initial begin
   errors=0;
   for(k=0;k<2000;k=k+1) begin
     a=$random;
     b=$random;
     if ((a[0]^b[0]) != 1'b1) b=b^1;
     #1;
     if (dr!==nr || di!==ni || dr!==sr || di!==si) begin
       $display("FAIL a=%h b=%h direct=%h,%h newton=%h,%h norm=%h,%h",
                 a,b,dr,di,nr,ni,sr,si);
       errors=errors+1;
     end
   end
   if(errors) $fatal(1,"%0d mismatches",errors);
   $display("PASS: 2000 Gaussian units at W=%0d",W);
   $finish;
 end
endmodule
