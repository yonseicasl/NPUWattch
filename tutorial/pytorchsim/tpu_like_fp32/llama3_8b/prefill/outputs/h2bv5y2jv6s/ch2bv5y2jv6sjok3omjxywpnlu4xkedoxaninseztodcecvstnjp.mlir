memref.global @buf0_spad : memref<8192xf32, 1>
memref.global @buf1_spad : memref<8192xf32, 1>
memref.global @buf2_spad : memref<8192xf32, 1>
func.func @kernel(%in_ptr0: memref<7340032xf32>,
                       %in_ptr1: memref<7340032xf32>,
                       %out_ptr0: memref<7340032xf32>)
{
    %const0 = arith.constant 0 : index
    %const1 = arith.constant 4 : index
    %const2 = arith.constant 2 : index
    %const3 = arith.constant 3 : index
    %alloc0 = memref.alloc() : memref<1xi32> // 0
    %alloc1 = memref.alloc() : memref<1xi32> // 1
    %alloc2 = memref.alloc() : memref<1xi32> // 2
    %spad0 = memref.get_global @buf0_spad : memref<8192xf32, 1>
    %spad1 = memref.get_global @buf1_spad : memref<8192xf32, 1>
    %spad2 = memref.get_global @buf2_spad : memref<8192xf32, 1>
    affine.for %index0 = 0 to 7340032 step 8192
    {
        memref.dma_start %in_ptr0[%index0], %spad0[%const0], %const2, %alloc0[%const0], %const0, %const1 : memref<7340032xf32>, memref<8192xf32, 1>, memref<1xi32> {dram_stride = [1], sram_stride = [1], padding = 0}
        memref.dma_start %in_ptr1[%index0], %spad1[%const0], %const2, %alloc1[%const0], %const0, %const1 : memref<7340032xf32>, memref<8192xf32, 1>, memref<1xi32> {dram_stride = [1], sram_stride = [1], padding = 0}
        affine.for %compute_idx = 0 to 64 step 4
        {
            %tmp1 = affine.vector_load %spad0[%compute_idx] : memref<8192xf32, 1>, vector<4xf32>
            %tmp10 = affine.vector_load %spad1[%compute_idx] : memref<8192xf32, 1>, vector<4xf32>
            %tmp2 = arith.constant 1.00000000000000000000 : f32
            %tmp3 = arith.negf %tmp1 : vector<4xf32>
            %tmp4 = math.exp %tmp3 : vector<4xf32>
            %tmp5 = vector.broadcast %tmp2 : f32 to vector<4xf32>
            %tmp6 = arith.addf %tmp5, %tmp4 : vector<4xf32>
            %tmp7 = arith.divf %tmp5, %tmp6 : vector<4xf32>
            %tmp8 = arith.mulf %tmp1, %tmp7 : vector<4xf32>
            %tmp11 = arith.mulf %tmp8, %tmp10 : vector<4xf32>
            affine.vector_store %tmp11, %spad2[%compute_idx] : memref<8192xf32, 1>, vector<4xf32>
        } {inner_loop=false}
        memref.dma_start %spad2[%const0], %out_ptr0[%index0], %const3, %alloc2[%const0], %const0, %const1 : memref<8192xf32, 1>, memref<7340032xf32>, memref<1xi32> {dram_stride = [1], sram_stride = [1], padding = 0}
    } {outer_loop=true}
    return
}
