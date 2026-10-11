memref.global @buf0_spad : memref<2x3584xf32, 1>
memref.global @buf1_spad : memref<1xf32, 1>
func.func @kernel(%in_ptr0: memref<3584xf32>,
                       %out_ptr0: memref<1xf32>)
{
    %const0 = arith.constant 0 : index
    %const1 = arith.constant 2 : index
    %const2 = arith.constant 0.0 : f32
    %const3 = vector.broadcast %const2 : f32 to vector<16xf32>
    %const4 = arith.constant 1 : index
    %const5 = arith.constant 3 : index
    %alloc0 = memref.alloc() : memref<1xi32> // 0
    %alloc1 = memref.alloc() : memref<1xi32> // 1
    %spad0 = memref.get_global @buf0_spad : memref<2x3584xf32, 1>
    %spad1 = memref.get_global @buf1_spad : memref<1xf32, 1>
    affine.for %index0 = 0 to 1 step 2
    {
        %tmp_acc0 = affine.for %index1 = 0 to 3584 step 3584 iter_args(%iter0 = %const3) -> (vector<16xf32>)
        {
            memref.dma_start %in_ptr0[%index1], %spad0[%const0,%const0], %const1, %alloc0[%const0], %const0, %const1 : memref<3584xf32>, memref<2x3584xf32, 1>, memref<1xi32> {dram_stride = [0, 1], sram_stride = [1, 2], padding = 0}
            %tmp_acc1 = affine.for %compute_idx = 0 to 7168 step 16 iter_args(%iter1 = %iter0) -> (vector<16xf32>)
            {
                %tmp1 = affine.vector_load %spad0[%const0,%compute_idx] : memref<2x3584xf32, 1>, vector<16xf32>
                %tmp2 = arith.mulf %tmp1, %tmp1 : vector<16xf32>
                %tmp3 = arith.addf %tmp2, %iter1 : vector<16xf32>
                affine.yield %tmp3 : vector<16xf32>
            } {inner_loop=false}
            affine.yield %tmp_acc1 : vector<16xf32>
        } {accumulation_loop=true}
        %tmp4 = vector.broadcast %const2 : f32 to vector<2xf32>
        %tmp5 = vector.shape_cast %tmp_acc0 : vector<16xf32> to vector<8x2xf32>
        %tmp6 = vector.multi_reduction <add>, %tmp5, %tmp4 [0] : vector<8x2xf32> to vector<2xf32>
        affine.vector_store %tmp6, %spad1[%const0] : memref<1xf32, 1>, vector<2xf32>
        memref.dma_start %spad1[%const0], %out_ptr0[%const0], %const5, %alloc1[%const0], %const0, %const4 : memref<1xf32, 1>, memref<1xf32>, memref<1xi32> {dram_stride = [0], sram_stride = [1], padding = 0}
    } {outer_loop=true}
    return
}
