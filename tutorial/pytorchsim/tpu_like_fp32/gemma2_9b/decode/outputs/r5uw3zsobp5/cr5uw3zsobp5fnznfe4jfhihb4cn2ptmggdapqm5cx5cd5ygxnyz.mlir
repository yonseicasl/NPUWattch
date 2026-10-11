memref.global @buf0_spad : memref<2048xf32, 1>
memref.global @buf1_spad : memref<2048xf32, 1>
memref.global @buf2_spad : memref<2048xf32, 1>
func.func @kernel(%in_ptr0: memref<14336xf32>,
                       %in_ptr1: memref<14336xf32>,
                       %out_ptr0: memref<14336xf32>)
{
    %const0 = arith.constant 0 : index
    %const1 = arith.constant 4 : index
    %const2 = arith.constant 2 : index
    %const3 = arith.constant 3 : index
    %alloc0 = memref.alloc() : memref<1xi32> // 0
    %alloc1 = memref.alloc() : memref<1xi32> // 1
    %alloc2 = memref.alloc() : memref<1xi32> // 2
    %spad0 = memref.get_global @buf0_spad : memref<2048xf32, 1>
    %spad1 = memref.get_global @buf1_spad : memref<2048xf32, 1>
    %spad2 = memref.get_global @buf2_spad : memref<2048xf32, 1>
    affine.for %index0 = 0 to 14336 step 2048
    {
        memref.dma_start %in_ptr0[%index0], %spad0[%const0], %const2, %alloc0[%const0], %const0, %const1 : memref<14336xf32>, memref<2048xf32, 1>, memref<1xi32> {dram_stride = [1], sram_stride = [1], padding = 0}
        memref.dma_start %in_ptr1[%index0], %spad1[%const0], %const2, %alloc1[%const0], %const0, %const1 : memref<14336xf32>, memref<2048xf32, 1>, memref<1xi32> {dram_stride = [1], sram_stride = [1], padding = 0}
        affine.for %compute_idx = 0 to 16 step 4
        {
            %tmp1 = affine.vector_load %spad0[%compute_idx] : memref<2048xf32, 1>, vector<4xf32>
            %tmp20 = affine.vector_load %spad1[%compute_idx] : memref<2048xf32, 1>, vector<4xf32>
            %tmp2 = arith.constant 0.50000000000000000000 : f32
            %tmp3 = vector.broadcast %tmp2 : f32 to vector<4xf32>
            %tmp4 = arith.mulf %tmp1, %tmp3 : vector<4xf32>
            %tmp5 = arith.mulf %tmp1, %tmp1 : vector<4xf32>
            %tmp6 = arith.mulf %tmp5, %tmp1 : vector<4xf32>
            %tmp7 = arith.constant 0.04471499999999999780 : f32
            %tmp8 = vector.broadcast %tmp7 : f32 to vector<4xf32>
            %tmp9 = arith.mulf %tmp6, %tmp8 : vector<4xf32>
            %tmp10 = arith.addf %tmp1, %tmp9 : vector<4xf32>
            %tmp11 = arith.constant 0.79788456080286540573 : f32
            %tmp12 = vector.broadcast %tmp11 : f32 to vector<4xf32>
            %tmp13 = arith.mulf %tmp10, %tmp12 : vector<4xf32>
            %tmp14 = math.tanh %tmp13 : vector<4xf32>
            %tmp15 = arith.constant 1.00000000000000000000 : f32
            %tmp16 = vector.broadcast %tmp15 : f32 to vector<4xf32>
            %tmp17 = arith.addf %tmp14, %tmp16 : vector<4xf32>
            %tmp18 = arith.mulf %tmp4, %tmp17 : vector<4xf32>
            %tmp21 = arith.mulf %tmp18, %tmp20 : vector<4xf32>
            affine.vector_store %tmp21, %spad2[%compute_idx] : memref<2048xf32, 1>, vector<4xf32>
        } {inner_loop=false}
        memref.dma_start %spad2[%const0], %out_ptr0[%index0], %const3, %alloc2[%const0], %const0, %const1 : memref<2048xf32, 1>, memref<14336xf32>, memref<1xi32> {dram_stride = [1], sram_stride = [1], padding = 0}
    } {outer_loop=true}
    return
}
