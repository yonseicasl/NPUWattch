memref.global @buf0_spad : memref<8192xf32, 1>
memref.global @buf1_spad : memref<8192xf32, 1>
func.func @kernel(%in_ptr0: memref<200704xf32>,
                       %out_ptr0: memref<200704xf32>)
{
    %const0 = arith.constant 0 : index
    %const1 = arith.constant 2 : index
    %const2 = arith.constant 3 : index
    %alloc0 = memref.alloc() : memref<1xi32> // 0
    %alloc1 = memref.alloc() : memref<1xi32> // 1
    %spad0 = memref.get_global @buf0_spad : memref<8192xf32, 1>
    %spad1 = memref.get_global @buf1_spad : memref<8192xf32, 1>
    affine.for %index0 = 0 to 200704 step 8192
    {
        memref.dma_start %in_ptr0[%index0], %spad0[%const0], %const1, %alloc0[%const0], %const0, %const1 : memref<200704xf32>, memref<8192xf32, 1>, memref<1xi32> {dram_stride = [1], sram_stride = [1], padding = 0}
        affine.for %compute_idx = 0 to 64 step 4
        {
            %tmp1 = affine.vector_load %spad0[%compute_idx] : memref<8192xf32, 1>, vector<4xf32>
            %tmp2 = arith.constant 0.00000000000000000000 : f32
            %tmp3 = vector.broadcast %tmp2 : f32 to vector<4xf32>
            %tmp4 = arith.maximumf %tmp1, %tmp3 : vector<4xf32>
            affine.vector_store %tmp4, %spad1[%compute_idx] : memref<8192xf32, 1>, vector<4xf32>
        } {inner_loop=false}
        memref.dma_start %spad1[%const0], %out_ptr0[%index0], %const2, %alloc1[%const0], %const0, %const1 : memref<8192xf32, 1>, memref<200704xf32>, memref<1xi32> {dram_stride = [1], sram_stride = [1], padding = 0}
    } {outer_loop=true}
    return
}
